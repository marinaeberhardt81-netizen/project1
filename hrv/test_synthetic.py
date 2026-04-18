"""
Synthetic validation of the rPPG/HRV algorithm without a camera.

Generates a fake PPG signal at a known heart rate with controlled HRV
and verifies that compute_hrv() recovers the expected metrics.

Run:  python hrv/test_synthetic.py
"""

import numpy as np
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from hrv.algorithm import SignalBuffer, compute_hrv


def make_synthetic_ppg(
    duration_sec: float = 40.0,
    fps: float = 30.0,
    mean_hr_bpm: float = 65.0,
    rmssd_ms: float = 40.0,
    noise_std: float = 0.05,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Produce a synthetic green-channel signal by summing sine waves whose
    instantaneous frequency jitters around mean_hr to produce a target RMSSD.
    """
    rng = np.random.default_rng(seed)
    n = int(duration_sec * fps)
    t = np.arange(n) / fps

    # RR jitter in seconds -> frequency jitter
    mean_rr_s = 60.0 / mean_hr_bpm
    rmssd_s = rmssd_ms / 1000.0

    # Generate RR series with roughly the desired RMSSD
    n_beats = int(duration_sec / mean_rr_s) + 2
    rr_jitter = rng.normal(0, rmssd_s / np.sqrt(2), n_beats)
    rr_series = np.clip(mean_rr_s + rr_jitter, 0.33, 1.5)
    beat_times = np.cumsum(rr_series)

    # Build phase signal from beat times
    phase = np.interp(t, beat_times, np.arange(len(beat_times))) * 2 * np.pi
    ppg = np.sin(phase) + 0.3 * np.sin(2 * phase)

    # Add harmonics and noise
    ppg += 0.1 * np.sin(3 * phase)
    ppg += rng.normal(0, noise_std, n)

    timestamps = t + 1_000_000.0  # arbitrary epoch offset
    return ppg, timestamps


def run_tests():
    print("=== Synthetic HRV Algorithm Tests ===\n")
    passed = 0
    failed = 0

    test_cases = [
        dict(mean_hr_bpm=60.0, rmssd_ms=50.0, label="Rest / high HRV"),
        dict(mean_hr_bpm=80.0, rmssd_ms=20.0, label="Active / low HRV"),
        dict(mean_hr_bpm=70.0, rmssd_ms=35.0, label="Normal"),
    ]

    for tc in test_cases:
        label = tc.pop("label")
        ppg, ts = make_synthetic_ppg(duration_sec=45.0, fps=30.0, **tc)

        buf = SignalBuffer(fps=30.0, window_sec=45.0)
        for v, t in zip(ppg, ts):
            buf.push(float(v), float(t))

        m = compute_hrv(buf, min_seconds=10.0)

        ok_hr = m is not None and abs(m.mean_hr_bpm - tc["mean_hr_bpm"]) < 8.0
        ok_rmssd = m is not None and abs(m.rmssd - tc["rmssd_ms"]) < 20.0

        status = "PASS" if (ok_hr and ok_rmssd) else "FAIL"
        if status == "PASS":
            passed += 1
        else:
            failed += 1

        print(f"[{status}] {label}")
        if m:
            print(f"       HR expected={tc['mean_hr_bpm']:.0f}  got={m.mean_hr_bpm:.1f} bpm")
            print(f"       RMSSD expected≈{tc['rmssd_ms']:.0f}  got={m.rmssd:.1f} ms")
            print(f"       SDNN={m.sdnn:.1f} ms  coherence={m.coherence_score:.1f}%  LF/HF={m.lf_hf_ratio:.2f}")
        else:
            print("       No metrics returned.")
        print()

    print(f"Results: {passed} passed, {failed} failed out of {passed+failed} tests.")
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
