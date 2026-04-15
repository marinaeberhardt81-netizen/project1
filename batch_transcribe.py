#!/usr/bin/env python3
"""
Batch-Transkription: Mehrere MP4-Dateien auf einmal verarbeiten.

Verwendung:
    python batch_transcribe.py videos/
    python batch_transcribe.py videos/ --model medium --format srt --language de
    python batch_transcribe.py video1.mp4 video2.mp4 video3.mp4
"""

import argparse
import sys
from pathlib import Path

try:
    import whisper
except ImportError:
    print("Fehler: openai-whisper ist nicht installiert.")
    print("Bitte führe aus: pip install -r requirements.txt")
    sys.exit(1)

from transcribe import FORMATS, MODELS, transcribe


VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def collect_videos(inputs: list[str]) -> list[Path]:
    """Sammelt alle Videodateien aus Pfaden und Verzeichnissen."""
    videos = []
    for inp in inputs:
        p = Path(inp)
        if p.is_dir():
            for ext in VIDEO_EXTENSIONS:
                videos.extend(sorted(p.glob(f"*{ext}")))
                videos.extend(sorted(p.glob(f"*{ext.upper()}")))
        elif p.is_file():
            if p.suffix.lower() in VIDEO_EXTENSIONS:
                videos.append(p)
            else:
                print(f"Warnung: '{p}' ist keine bekannte Videodatei, wird übersprungen.")
        else:
            print(f"Warnung: '{p}' nicht gefunden, wird übersprungen.")

    # Duplikate entfernen, Reihenfolge beibehalten
    seen = set()
    unique = []
    for v in videos:
        resolved = v.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(v)
    return unique


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mehrere MP4-Videos auf einmal transkribieren",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python batch_transcribe.py videos/
  python batch_transcribe.py *.mp4 --model small --language de
  python batch_transcribe.py a.mp4 b.mp4 --format srt
        """,
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="MP4-Dateien oder Verzeichnisse mit MP4-Dateien",
    )
    parser.add_argument(
        "--model", "-m",
        choices=MODELS,
        default="base",
        help="Whisper-Modell (Standard: base)",
    )
    parser.add_argument(
        "--language", "-l",
        default=None,
        help="Sprache erzwingen, z.B. 'de', 'en' (Standard: automatisch)",
    )
    parser.add_argument(
        "--format", "-f",
        choices=FORMATS,
        default="txt",
        dest="fmt",
        help="Ausgabeformat (Standard: txt)",
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=None,
        help="Ausgabeverzeichnis (Standard: neben den Videodateien)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Bereits transkribierte Dateien überspringen",
    )

    args = parser.parse_args()

    videos = collect_videos(args.inputs)
    if not videos:
        print("Keine Videodateien gefunden.")
        sys.exit(1)

    output_dir = Path(args.output_dir) if args.output_dir else None
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Gefundene Videos: {len(videos)}")
    print(f"Modell: {args.model} | Format: {args.fmt}")
    if args.language:
        print(f"Sprache: {args.language}")
    print("=" * 50)

    # Modell einmal laden und für alle Videos wiederverwenden
    print(f"Lade Whisper-Modell '{args.model}'...")
    model = whisper.load_model(args.model)

    errors = []
    for idx, video in enumerate(videos, start=1):
        print(f"\n[{idx}/{len(videos)}] {video.name}")
        print("-" * 40)

        # Zieldatei bestimmen
        dest_dir = output_dir if output_dir else video.parent
        fmt_ext = "txt" if args.fmt == "all" else args.fmt

        if args.skip_existing:
            target = dest_dir / f"{video.stem}.{fmt_ext}"
            if target.exists():
                print(f"  Übersprungen (existiert bereits): {target}")
                continue

        try:
            transcribe(
                video_path=video,
                model_name=args.model,
                language=args.language,
                fmt=args.fmt,
                output_path=dest_dir / f"{video.stem}.{fmt_ext}" if output_dir else None,
            )
        except SystemExit:
            errors.append(video)
            print(f"  FEHLER bei {video.name}")

    print("\n" + "=" * 50)
    print(f"Abgeschlossen: {len(videos) - len(errors)}/{len(videos)} erfolgreich")
    if errors:
        print("Fehler bei:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
