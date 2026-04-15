# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller-Spec für MP4 Transkription GUI
# Ausführen mit:  pyinstaller transcribe_gui.spec
#
import io
import os
import shutil
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_all

# ---------------------------------------------------------------------------
# ffmpeg-Binary beschaffen und direkt einbündeln
# (static-ffmpeg NICHT zur Laufzeit aufrufen – sys.stdout ist None in
#  windowed EXEs und würde crashen)
# ---------------------------------------------------------------------------
def _get_ffmpeg_binaries():
    """
    Versucht ffmpeg.exe / ffprobe.exe über static-ffmpeg zu finden.
    Gibt eine Liste von (src_path, dest_folder) für PyInstaller zurück.
    """
    bins = []
    try:
        # sys.stdout/stderr ggf. None → temporär umleiten
        _null = io.StringIO()
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = _null
        sys.stderr = _null
        try:
            import static_ffmpeg
            static_ffmpeg.add_paths()
        finally:
            sys.stdout = old_out
            sys.stderr = old_err

        for name in ("ffmpeg", "ffprobe", "ffmpeg.exe", "ffprobe.exe"):
            found = shutil.which(name)
            if found:
                bins.append((found, "."))
    except Exception as exc:
        print(f"[spec] ffmpeg über static-ffmpeg nicht gefunden: {exc}", file=sys.stderr or sys.__stderr__)
    return bins


ffmpeg_binaries = _get_ffmpeg_binaries()

# ---------------------------------------------------------------------------
# Whisper-Datendateien (Vokabular, Konfigurationen)
# ---------------------------------------------------------------------------
whisper_datas, whisper_binaries, whisper_hiddenimports = collect_all("whisper")

# tiktoken-Erweiterungen (von Whisper benötigt)
tiktoken_datas, tiktoken_binaries, tiktoken_hiddenimports = collect_all("tiktoken_extensions")

# tqdm (Fortschrittsanzeigen in Whisper)
tqdm_datas = collect_data_files("tqdm")

all_datas = whisper_datas + tiktoken_datas + tqdm_datas
all_binaries = ffmpeg_binaries + whisper_binaries + tiktoken_binaries
all_hidden = (
    whisper_hiddenimports
    + tiktoken_hiddenimports
    + [
        "whisper",
        "whisper.audio",
        "whisper.decoding",
        "whisper.model",
        "whisper.tokenizer",
        "whisper.transcribe",
        "whisper.utils",
        "tiktoken",
        "tiktoken_extensions",
        "ffmpeg",
        "tqdm",
        "numpy",
        "torch",
    ]
)

a = Analysis(
    ["transcribe_gui.py"],
    pathex=[],
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Unnötige Module ausschließen (reduziert Größe)
        "matplotlib",
        "scipy",
        "IPython",
        "jupyter",
        "PIL",
        "cv2",
        "sklearn",
        "pandas",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # --onedir (schneller Start als --onefile)
    name="MP4-Transkription",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                # UPX-Komprimierung wenn verfügbar
    console=False,           # Kein schwarzes CMD-Fenster
    icon="icon.ico" if Path("icon.ico").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MP4-Transkription",
)
