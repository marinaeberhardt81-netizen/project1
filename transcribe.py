#!/usr/bin/env python3
"""
MP4 Video Transcription Tool
Transkribiert MP4-Videos lokal mit OpenAI Whisper (kein API-Key erforderlich).

Verwendung:
    python transcribe.py video.mp4
    python transcribe.py video.mp4 --model medium --language de --format srt
    python transcribe.py video.mp4 --output ergebnis.txt
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

try:
    import whisper
except ImportError:
    print("Fehler: openai-whisper ist nicht installiert.")
    print("Bitte führe aus: pip install -r requirements.txt")
    sys.exit(1)

try:
    import ffmpeg
except ImportError:
    print("Fehler: ffmpeg-python ist nicht installiert.")
    print("Bitte führe aus: pip install -r requirements.txt")
    sys.exit(1)


MODELS = ["tiny", "base", "small", "medium", "large"]
FORMATS = ["txt", "srt", "vtt", "json", "all"]


def extract_audio(video_path: Path, audio_path: Path) -> None:
    """Extrahiert die Audiospur aus einem MP4-Video."""
    try:
        (
            ffmpeg
            .input(str(video_path))
            .output(str(audio_path), ac=1, ar=16000, acodec="pcm_s16le")
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as e:
        print(f"Fehler beim Extrahieren der Audiospur: {e.stderr.decode()}")
        sys.exit(1)


def format_timestamp(seconds: float) -> str:
    """Konvertiert Sekunden in SRT-Zeitformat HH:MM:SS,mmm."""
    millis = int((seconds % 1) * 1000)
    s = int(seconds)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:02d},{millis:03d}"


def format_timestamp_vtt(seconds: float) -> str:
    """Konvertiert Sekunden in WebVTT-Zeitformat HH:MM:SS.mmm."""
    return format_timestamp(seconds).replace(",", ".")


def to_txt(result: dict) -> str:
    """Gibt den reinen Transkriptionstext zurück."""
    return result["text"].strip()


def to_srt(result: dict) -> str:
    """Konvertiert Whisper-Ergebnis in SRT-Untertitelformat."""
    lines = []
    for i, seg in enumerate(result["segments"], start=1):
        start = format_timestamp(seg["start"])
        end = format_timestamp(seg["end"])
        text = seg["text"].strip()
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def to_vtt(result: dict) -> str:
    """Konvertiert Whisper-Ergebnis in WebVTT-Format."""
    lines = ["WEBVTT\n"]
    for seg in result["segments"]:
        start = format_timestamp_vtt(seg["start"])
        end = format_timestamp_vtt(seg["end"])
        text = seg["text"].strip()
        lines.append(f"{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def to_json(result: dict) -> str:
    """Gibt das vollständige Whisper-Ergebnis als JSON zurück."""
    output = {
        "language": result.get("language", ""),
        "text": result["text"].strip(),
        "segments": [
            {
                "id": seg["id"],
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"].strip(),
            }
            for seg in result["segments"]
        ],
    }
    return json.dumps(output, ensure_ascii=False, indent=2)


def save_output(content: str, output_path: Path) -> None:
    """Speichert den Inhalt in eine Datei."""
    output_path.write_text(content, encoding="utf-8")
    print(f"  Gespeichert: {output_path}")


def transcribe(
    video_path: Path,
    model_name: str = "base",
    language: str | None = None,
    fmt: str = "txt",
    output_path: Path | None = None,
) -> None:
    """Hauptfunktion: Audio extrahieren, transkribieren und ausgeben."""

    if not video_path.exists():
        print(f"Fehler: Datei nicht gefunden: {video_path}")
        sys.exit(1)

    if video_path.suffix.lower() not in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
        print(f"Warnung: Unbekanntes Dateiformat '{video_path.suffix}'. Versuche es trotzdem...")

    print(f"Video:   {video_path}")
    print(f"Modell:  {model_name}  (tiny=schnell/ungenau  large=langsam/genau)")
    if language:
        print(f"Sprache: {language}")
    print()

    # Schritt 1: Audio extrahieren
    print("Schritt 1/3 – Audiospur wird extrahiert...")
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = Path(tmpdir) / "audio.wav"
        extract_audio(video_path, audio_path)

        # Schritt 2: Whisper-Modell laden
        print(f"Schritt 2/3 – Whisper-Modell '{model_name}' wird geladen...")
        model = whisper.load_model(model_name)

        # Schritt 3: Transkription
        print("Schritt 3/3 – Transkription läuft...")
        kwargs = {}
        if language:
            kwargs["language"] = language
        result = model.transcribe(str(audio_path), **kwargs)

    print(f"\nErkannte Sprache: {result.get('language', 'unbekannt').upper()}\n")

    # Ausgabe erstellen
    stem = video_path.stem
    parent = output_path.parent if output_path else video_path.parent

    formats_to_write = FORMATS[:-1] if fmt == "all" else [fmt]

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

        if output_path and fmt != "all":
            dest = output_path
        else:
            dest = parent / f"{stem}.{f}"

        save_output(content, dest)

    print("\nFertig!")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MP4-Videos lokal transkribieren mit OpenAI Whisper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python transcribe.py vortrag.mp4
  python transcribe.py vortrag.mp4 --model medium --language de
  python transcribe.py vortrag.mp4 --format srt --output untertitel.srt
  python transcribe.py vortrag.mp4 --format all

Modelle (Größe / Genauigkeit / Geschwindigkeit):
  tiny   – ~39 MB  – schnell, weniger genau
  base   – ~74 MB  – gut für einfache Sprache  [Standard]
  small  – ~244 MB – gute Balance
  medium – ~769 MB – sehr genau
  large  – ~1550 MB– höchste Genauigkeit, langsam
        """,
    )
    parser.add_argument("video", help="Pfad zur MP4-Datei")
    parser.add_argument(
        "--model", "-m",
        choices=MODELS,
        default="base",
        help="Whisper-Modell (Standard: base)",
    )
    parser.add_argument(
        "--language", "-l",
        default=None,
        help="Sprache erzwingen, z.B. 'de', 'en', 'fr' (Standard: automatisch erkennen)",
    )
    parser.add_argument(
        "--format", "-f",
        choices=FORMATS,
        default="txt",
        dest="fmt",
        help="Ausgabeformat (Standard: txt)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Ausgabedatei (Standard: <videoname>.<format> im selben Ordner)",
    )

    args = parser.parse_args()

    video_path = Path(args.video)
    output_path = Path(args.output) if args.output else None

    transcribe(
        video_path=video_path,
        model_name=args.model,
        language=args.language,
        fmt=args.fmt,
        output_path=output_path,
    )


if __name__ == "__main__":
    main()
