"""
Live HRV measurement via webcam (rPPG).

Usage:
  python hrv/measure.py
  python hrv/measure.py --camera 1      # use second camera
  python hrv/measure.py --window 60     # 60-second analysis window

Controls (OpenCV window):
  q  – quit
  s  – print current metrics to console and save PSD plot
"""

import argparse
import time
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from hrv.algorithm import SignalBuffer, compute_hrv, HRVMetrics

RECALC_EVERY_FRAMES = 30   # ~1 s at 30 fps
MIN_SECONDS_FOR_METRICS = 10.0


def extract_forehead_roi(frame: np.ndarray, cascade: cv2.CascadeClassifier):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))
    if len(faces) == 0:
        return None, None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    # Forehead: center 60% width, top 25% height
    fx = x + int(w * 0.20)
    fy = y + int(h * 0.05)
    fw = int(w * 0.60)
    fh = int(h * 0.25)
    return frame[fy : fy + fh, fx : fx + fw], (x, y, w, h, fx, fy, fw, fh)


def draw_overlay(frame: np.ndarray, bbox, metrics, buf: SignalBuffer) -> np.ndarray:
    y = 28
    cv2.putText(
        frame,
        f"Buffer: {buf.duration_sec:.0f}s  FPS: {buf.actual_fps():.0f}",
        (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 180, 180), 1,
    )
    y += 24

    if bbox:
        x0, y0, w0, h0, fx, fy, fw, fh = bbox
        cv2.rectangle(frame, (x0, y0), (x0 + w0, y0 + h0), (0, 220, 0), 2)
        cv2.rectangle(frame, (fx, fy), (fx + fw, fy + fh), (255, 80, 0), 2)
        cv2.putText(frame, "ROI", (fx, fy - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 80, 0), 1)

    if metrics:
        items = [
            (f"HR:        {metrics.mean_hr_bpm:.0f} bpm", (50, 220, 50)),
            (f"RMSSD:     {metrics.rmssd:.1f} ms",         (50, 220, 50)),
            (f"SDNN:      {metrics.sdnn:.1f} ms",           (50, 220, 50)),
            (f"Coherence: {metrics.coherence_score:.1f}%",  (0, 200, 255)),
            (f"LF/HF:     {metrics.lf_hf_ratio:.2f}",       (50, 220, 50)),
        ]
        for text, color in items:
            cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
            y += 28
    else:
        cv2.putText(
            frame, "Collecting data…", (10, y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.70, (0, 200, 255), 2,
        )

    return frame


def save_psd(metrics: HRVMetrics) -> None:
    try:
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.plot(metrics.psd_freqs, metrics.psd_values, color="steelblue")
        ax.axvspan(0.04, 0.15, alpha=0.18, color="blue", label="LF (0.04–0.15 Hz)")
        ax.axvspan(0.15, 0.40, alpha=0.18, color="red",  label="HF (0.15–0.40 Hz)")
        ax.axvspan(0.05, 0.15, alpha=0.25, color="lime", label="Coherence band (0.05–0.15 Hz)")
        ax.set_xlabel("Frequency (Hz)")
        ax.set_ylabel("Power (ms²/Hz)")
        ax.set_title("HRV Power Spectral Density")
        ax.legend()
        path = "hrv_psd.png"
        fig.savefig(path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        print(f"  PSD plot saved → {path}")
    except ImportError:
        print("  (matplotlib not installed – PSD plot skipped)")


def print_metrics(m: HRVMetrics) -> None:
    print("\n--- HRV Metrics ---")
    print(f"  Mean HR:    {m.mean_hr_bpm:.1f} bpm")
    print(f"  Mean RR:    {m.mean_rr_ms:.1f} ms")
    print(f"  RMSSD:      {m.rmssd:.1f} ms")
    print(f"  SDNN:       {m.sdnn:.1f} ms")
    print(f"  LF power:   {m.lf_power:.4f} ms²")
    print(f"  HF power:   {m.hf_power:.4f} ms²")
    print(f"  LF/HF:      {m.lf_hf_ratio:.3f}")
    print(f"  Coherence:  {m.coherence_score:.1f} %")
    print(f"  RR samples: {len(m.rr_intervals)}")


def main(camera_idx: int = 0, window_sec: float = 30.0) -> None:
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)

    cap = cv2.VideoCapture(camera_idx)
    if not cap.isOpened():
        print(f"Error: cannot open camera index {camera_idx}.")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)

    fps_hint = cap.get(cv2.CAP_PROP_FPS) or 30.0
    buf = SignalBuffer(fps=fps_hint, window_sec=window_sec)
    metrics = None
    frame_count = 0

    print("HRV Measurement running.  q = quit,  s = save metrics")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        ts = time.time()
        roi, bbox = extract_forehead_roi(frame, face_cascade)

        if roi is not None and roi.size > 0:
            buf.push(float(np.mean(roi[:, :, 1])), ts)

        frame_count += 1
        if frame_count % RECALC_EVERY_FRAMES == 0:
            metrics = compute_hrv(buf, min_seconds=MIN_SECONDS_FOR_METRICS)

        frame = draw_overlay(frame, bbox, metrics, buf)
        cv2.imshow("HRV Measurement", frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("s") and metrics:
            print_metrics(metrics)
            if len(metrics.psd_freqs) > 0:
                save_psd(metrics)

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Live HRV via rPPG")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--window", type=float, default=30.0, help="Analysis window in seconds")
    args = parser.parse_args()
    main(camera_idx=args.camera, window_sec=args.window)
