"""
rPPG-based HRV algorithm — camera-agnostic core.

Pipeline:
  raw green-channel samples
    -> bandpass filter (0.7–3 Hz)
    -> peak detection -> RR intervals (ms)
    -> time-domain HRV (RMSSD, SDNN)
    -> frequency-domain HRV (LF, HF, coherence score)
"""

import numpy as np
from scipy import signal
from scipy.fft import fft, fftfreq
from dataclasses import dataclass, field
from collections import deque
from typing import Optional

HR_MIN_HZ = 0.7    # 42 bpm
HR_MAX_HZ = 3.0    # 180 bpm
COHERENCE_CENTER_HZ = 0.10
COHERENCE_BAND_HZ = 0.05


@dataclass
class HRVMetrics:
    mean_hr_bpm: float = 0.0
    mean_rr_ms: float = 0.0
    rmssd: float = 0.0
    sdnn: float = 0.0
    lf_power: float = 0.0
    hf_power: float = 0.0
    lf_hf_ratio: float = 0.0
    coherence_score: float = 0.0   # 0–100 %, HeartMath-style
    rr_intervals: list = field(default_factory=list)
    psd_freqs: np.ndarray = field(default_factory=lambda: np.array([]))
    psd_values: np.ndarray = field(default_factory=lambda: np.array([]))


class SignalBuffer:
    """Rolling buffer for raw rPPG green-channel samples."""

    def __init__(self, fps: float = 30.0, window_sec: float = 30.0):
        self.fps = fps
        maxlen = int(fps * window_sec)
        self._samples: deque = deque(maxlen=maxlen)
        self._timestamps: deque = deque(maxlen=maxlen)

    def push(self, value: float, timestamp: float) -> None:
        self._samples.append(value)
        self._timestamps.append(timestamp)

    @property
    def samples(self) -> np.ndarray:
        return np.array(self._samples)

    @property
    def timestamps(self) -> np.ndarray:
        return np.array(self._timestamps)

    @property
    def duration_sec(self) -> float:
        ts = self.timestamps
        return float(ts[-1] - ts[0]) if len(ts) > 1 else 0.0

    def actual_fps(self) -> float:
        ts = self.timestamps
        if len(ts) < 2 or self.duration_sec <= 0:
            return self.fps
        return len(ts) / self.duration_sec


def bandpass_filter(samples: np.ndarray, fps: float) -> Optional[np.ndarray]:
    nyq = fps / 2.0
    low = HR_MIN_HZ / nyq
    high = HR_MAX_HZ / nyq
    low = np.clip(low, 1e-3, 0.98)
    high = np.clip(high, 1e-3, 0.98)
    if low >= high:
        return None
    b, a = signal.butter(4, [low, high], btype="band")
    return signal.filtfilt(b, a, signal.detrend(samples))


def detect_peaks(filtered: np.ndarray, fps: float) -> np.ndarray:
    min_dist = int(fps * 0.4)  # max 150 bpm
    prominence = 0.15 * np.std(filtered)
    peaks, _ = signal.find_peaks(filtered, distance=min_dist, prominence=prominence)
    return peaks


def rr_from_peaks(peak_indices: np.ndarray, timestamps: np.ndarray) -> np.ndarray:
    peak_times = timestamps[peak_indices]
    rr = np.diff(peak_times) * 1000  # ms
    return rr[(rr > 300) & (rr < 2000)]


def _psd(rr_ms: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Interpolate RR series to 4 Hz and compute Welch PSD."""
    fs = 4.0
    rr_times = np.cumsum(rr_ms) / 1000.0
    rr_times = np.insert(rr_times, 0, 0)[:-1]
    t_uniform = np.arange(rr_times[0], rr_times[-1], 1.0 / fs)
    if len(t_uniform) < 16:
        return np.array([]), np.array([])
    rr_interp = np.interp(t_uniform, rr_times, rr_ms)
    rr_interp = signal.detrend(rr_interp)
    nperseg = min(len(rr_interp), 128)
    freqs, psd = signal.welch(rr_interp, fs=fs, nperseg=nperseg)
    return freqs, psd


def _band_power(freqs: np.ndarray, psd: np.ndarray, f_lo: float, f_hi: float) -> float:
    mask = (freqs >= f_lo) & (freqs < f_hi)
    if not np.any(mask):
        return 0.0
    integrate = np.trapezoid if hasattr(np, "trapezoid") else np.trapz
    return float(integrate(psd[mask], freqs[mask]))


def compute_hrv(buf: SignalBuffer, min_seconds: float = 10.0) -> Optional[HRVMetrics]:
    if buf.duration_sec < min_seconds:
        return None

    fps = buf.actual_fps()
    filtered = bandpass_filter(buf.samples, fps)
    if filtered is None:
        return None

    peaks = detect_peaks(filtered, fps)
    if len(peaks) < 4:
        return None

    rr = rr_from_peaks(peaks, buf.timestamps)
    if len(rr) < 4:
        return None

    m = HRVMetrics()
    m.rr_intervals = rr.tolist()
    m.mean_rr_ms = float(np.mean(rr))
    m.mean_hr_bpm = 60_000.0 / m.mean_rr_ms
    m.rmssd = float(np.sqrt(np.mean(np.diff(rr) ** 2)))
    m.sdnn = float(np.std(rr))

    if len(rr) >= 10:
        freqs, psd = _psd(rr)
        if len(freqs) > 0:
            m.psd_freqs = freqs
            m.psd_values = psd
            total = _band_power(freqs, psd, 0.003, 0.4) or 1.0
            m.lf_power = _band_power(freqs, psd, 0.04, 0.15)
            m.hf_power = _band_power(freqs, psd, 0.15, 0.40)
            m.lf_hf_ratio = m.lf_power / m.hf_power if m.hf_power > 0 else 0.0
            coh = _band_power(
                freqs, psd,
                COHERENCE_CENTER_HZ - COHERENCE_BAND_HZ,
                COHERENCE_CENTER_HZ + COHERENCE_BAND_HZ,
            )
            m.coherence_score = min(100.0, coh / total * 100.0)

    return m
