#!/usr/bin/env python3
"""
MP4 Transcription Tool – Grafische Benutzeroberfläche (tkinter)
Wird zu einer Windows-EXE gebündelt via PyInstaller.
"""

import json
import os
import queue
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk


# ---------------------------------------------------------------------------
# ffmpeg-Pfad setzen (static-ffmpeg liefert ffmpeg ohne Systeminstallation)
# ---------------------------------------------------------------------------
def _setup_ffmpeg() -> None:
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except ImportError:
        pass  # Systemweites ffmpeg wird versucht


_setup_ffmpeg()

# ---------------------------------------------------------------------------
# Imports der Transkriptions-Logik
# ---------------------------------------------------------------------------
try:
    import ffmpeg
    import whisper
except ImportError as exc:
    import tkinter.messagebox as _mb
    _root = tk.Tk()
    _root.withdraw()
    _mb.showerror(
        "Abhängigkeit fehlt",
        f"Bitte 'pip install -r requirements.txt' ausführen.\n\nFehler: {exc}",
    )
    sys.exit(1)

from transcribe import to_json, to_srt, to_txt, to_vtt, extract_audio

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------
MODELS = ["tiny", "base", "small", "medium", "large"]
FORMATS = ["txt", "srt", "vtt", "json", "all"]
LANGUAGES = [
    ("Automatisch erkennen", ""),
    ("Deutsch", "de"),
    ("Englisch", "en"),
    ("Französisch", "fr"),
    ("Spanisch", "es"),
    ("Italienisch", "it"),
    ("Portugiesisch", "pt"),
    ("Niederländisch", "nl"),
    ("Polnisch", "pl"),
    ("Russisch", "ru"),
    ("Japanisch", "ja"),
    ("Chinesisch", "zh"),
    ("Arabisch", "ar"),
    ("Türkisch", "tr"),
]

# ---------------------------------------------------------------------------
# Haupt-GUI
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("MP4 Transkription")
        self.resizable(False, False)
        self._q: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._build_ui()
        self.after(100, self._poll_queue)

    # ------------------------------------------------------------------
    # UI-Aufbau
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 5}

        # ── Dateiauswahl ─────────────────────────────────────────────
        frame_file = ttk.LabelFrame(self, text="Videodatei")
        frame_file.grid(row=0, column=0, columnspan=3, sticky="ew", **pad)

        self._file_var = tk.StringVar()
        ttk.Entry(frame_file, textvariable=self._file_var, width=55).grid(
            row=0, column=0, padx=5, pady=5
        )
        ttk.Button(frame_file, text="Durchsuchen…", command=self._browse_file).grid(
            row=0, column=1, padx=5
        )

        # ── Einstellungen ─────────────────────────────────────────────
        frame_opts = ttk.LabelFrame(self, text="Einstellungen")
        frame_opts.grid(row=1, column=0, columnspan=3, sticky="ew", **pad)

        ttk.Label(frame_opts, text="Modell:").grid(row=0, column=0, sticky="w", padx=5, pady=4)
        self._model_var = tk.StringVar(value="base")
        model_cb = ttk.Combobox(
            frame_opts, textvariable=self._model_var, values=MODELS, width=10, state="readonly"
        )
        model_cb.grid(row=0, column=1, sticky="w", padx=5)
        ttk.Label(
            frame_opts,
            text="tiny=schnell  base=Standard  small/medium=genauer  large=maximal",
            foreground="gray",
        ).grid(row=0, column=2, sticky="w", padx=5)

        ttk.Label(frame_opts, text="Sprache:").grid(row=1, column=0, sticky="w", padx=5, pady=4)
        self._lang_var = tk.StringVar(value="Automatisch erkennen")
        lang_cb = ttk.Combobox(
            frame_opts,
            textvariable=self._lang_var,
            values=[l[0] for l in LANGUAGES],
            width=22,
            state="readonly",
        )
        lang_cb.grid(row=1, column=1, columnspan=2, sticky="w", padx=5)

        ttk.Label(frame_opts, text="Format:").grid(row=2, column=0, sticky="w", padx=5, pady=4)
        self._fmt_var = tk.StringVar(value="txt")
        fmt_cb = ttk.Combobox(
            frame_opts,
            textvariable=self._fmt_var,
            values=FORMATS,
            width=10,
            state="readonly",
        )
        fmt_cb.grid(row=2, column=1, sticky="w", padx=5)
        ttk.Label(
            frame_opts,
            text="all = txt + srt + vtt + json",
            foreground="gray",
        ).grid(row=2, column=2, sticky="w", padx=5)

        ttk.Label(frame_opts, text="Ausgabeordner:").grid(
            row=3, column=0, sticky="w", padx=5, pady=4
        )
        self._outdir_var = tk.StringVar(value="(gleicher Ordner wie das Video)")
        ttk.Entry(frame_opts, textvariable=self._outdir_var, width=40).grid(
            row=3, column=1, sticky="w", padx=5
        )
        ttk.Button(frame_opts, text="Wählen…", command=self._browse_outdir).grid(
            row=3, column=2, padx=5
        )

        # ── Fortschritt ───────────────────────────────────────────────
        frame_prog = ttk.LabelFrame(self, text="Fortschritt")
        frame_prog.grid(row=2, column=0, columnspan=3, sticky="ew", **pad)

        self._progress = ttk.Progressbar(frame_prog, mode="indeterminate", length=500)
        self._progress.grid(row=0, column=0, padx=5, pady=5, sticky="ew")

        self._log = scrolledtext.ScrolledText(
            frame_prog, height=12, width=65, state="disabled", font=("Courier", 9)
        )
        self._log.grid(row=1, column=0, padx=5, pady=5)

        # ── Buttons ───────────────────────────────────────────────────
        frame_btn = ttk.Frame(self)
        frame_btn.grid(row=3, column=0, columnspan=3, pady=8)

        self._start_btn = ttk.Button(
            frame_btn, text="Transkription starten", command=self._start, width=25
        )
        self._start_btn.grid(row=0, column=0, padx=8)
        ttk.Button(frame_btn, text="Log leeren", command=self._clear_log, width=12).grid(
            row=0, column=1, padx=8
        )

    # ------------------------------------------------------------------
    # Dialoge
    # ------------------------------------------------------------------
    def _browse_file(self) -> None:
        path = filedialog.askopenfilename(
            title="MP4-Datei auswählen",
            filetypes=[
                ("Videodateien", "*.mp4 *.mov *.avi *.mkv *.webm"),
                ("Alle Dateien", "*.*"),
            ],
        )
        if path:
            self._file_var.set(path)

    def _browse_outdir(self) -> None:
        path = filedialog.askdirectory(title="Ausgabeordner auswählen")
        if path:
            self._outdir_var.set(path)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------
    def _log_msg(self, msg: str) -> None:
        self._log.configure(state="normal")
        self._log.insert(tk.END, msg + "\n")
        self._log.see(tk.END)
        self._log.configure(state="disabled")

    def _clear_log(self) -> None:
        self._log.configure(state="normal")
        self._log.delete("1.0", tk.END)
        self._log.configure(state="disabled")

    # ------------------------------------------------------------------
    # Queue-basierte Kommunikation mit dem Worker-Thread
    # ------------------------------------------------------------------
    def _poll_queue(self) -> None:
        try:
            while True:
                msg_type, payload = self._q.get_nowait()
                if msg_type == "log":
                    self._log_msg(payload)
                elif msg_type == "done":
                    self._progress.stop()
                    self._start_btn.configure(state="normal")
                    messagebox.showinfo("Fertig", payload)
                elif msg_type == "error":
                    self._progress.stop()
                    self._start_btn.configure(state="normal")
                    messagebox.showerror("Fehler", payload)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    # ------------------------------------------------------------------
    # Transkription (in separatem Thread)
    # ------------------------------------------------------------------
    def _start(self) -> None:
        video_str = self._file_var.get().strip()
        if not video_str:
            messagebox.showwarning("Kein Video", "Bitte zuerst eine Videodatei auswählen.")
            return

        video_path = Path(video_str)
        if not video_path.exists():
            messagebox.showerror("Datei nicht gefunden", f"{video_path}")
            return

        # Sprache aus Anzeigename ermitteln
        lang_display = self._lang_var.get()
        lang_code = next((c for name, c in LANGUAGES if name == lang_display), "")

        outdir_str = self._outdir_var.get()
        if outdir_str.startswith("("):
            output_dir = video_path.parent
        else:
            output_dir = Path(outdir_str)
            output_dir.mkdir(parents=True, exist_ok=True)

        self._start_btn.configure(state="disabled")
        self._progress.start(10)

        self._thread = threading.Thread(
            target=self._worker,
            args=(video_path, self._model_var.get(), lang_code or None, self._fmt_var.get(), output_dir),
            daemon=True,
        )
        self._thread.start()

    def _worker(
        self,
        video_path: Path,
        model_name: str,
        language: str | None,
        fmt: str,
        output_dir: Path,
    ) -> None:
        q = self._q
        try:
            q.put(("log", f"Video:   {video_path.name}"))
            q.put(("log", f"Modell:  {model_name}"))
            q.put(("log", f"Sprache: {language or 'automatisch'}"))
            q.put(("log", f"Format:  {fmt}"))
            q.put(("log", ""))

            q.put(("log", "Schritt 1/3 – Audiospur wird extrahiert…"))
            with tempfile.TemporaryDirectory() as tmpdir:
                audio_path = Path(tmpdir) / "audio.wav"
                extract_audio(video_path, audio_path)

                q.put(("log", f"Schritt 2/3 – Whisper-Modell '{model_name}' wird geladen…"))
                model = whisper.load_model(model_name)

                q.put(("log", "Schritt 3/3 – Transkription läuft…"))
                kwargs = {}
                if language:
                    kwargs["language"] = language
                result = model.transcribe(str(audio_path), **kwargs)

            detected = result.get("language", "?").upper()
            q.put(("log", f"Erkannte Sprache: {detected}"))
            q.put(("log", ""))

            formats_to_write = ["txt", "srt", "vtt", "json"] if fmt == "all" else [fmt]
            saved = []
            for f in formats_to_write:
                if f == "txt":
                    content = to_txt(result)
                elif f == "srt":
                    content = to_srt(result)
                elif f == "vtt":
                    content = to_vtt(result)
                elif f == "json":
                    content = to_json(result)
                else:
                    continue
                dest = output_dir / f"{video_path.stem}.{f}"
                dest.write_text(content, encoding="utf-8")
                q.put(("log", f"Gespeichert: {dest}"))
                saved.append(str(dest))

            q.put(("done", f"Transkription abgeschlossen!\n\n" + "\n".join(saved)))

        except Exception as exc:  # noqa: BLE001
            q.put(("error", f"Fehler: {exc}"))


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------
def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
