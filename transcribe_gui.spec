# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller-Spec für MP4 Transkription GUI
# Ausführen mit:  pyinstaller transcribe_gui.spec
#
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_all

# Whisper-Datendateien (Vokabular, Konfigurationen)
whisper_datas, whisper_binaries, whisper_hiddenimports = collect_all("whisper")

# tiktoken-Erweiterungen (von Whisper benötigt)
tiktoken_datas, tiktoken_binaries, tiktoken_hiddenimports = collect_all("tiktoken_extensions")

# tqdm (Fortschrittsanzeigen in Whisper)
tqdm_datas = collect_data_files("tqdm")

# static-ffmpeg (liefert ffmpeg.exe/ffprobe.exe ohne Systeminstallation)
try:
    sfmpeg_datas, sfmpeg_binaries, sfmpeg_hidden = collect_all("static_ffmpeg")
except Exception:
    sfmpeg_datas, sfmpeg_binaries, sfmpeg_hidden = [], [], []

all_datas = (
    whisper_datas
    + tiktoken_datas
    + tqdm_datas
    + sfmpeg_datas
)
all_binaries = whisper_binaries + tiktoken_binaries + sfmpeg_binaries
all_hidden = (
    whisper_hiddenimports
    + tiktoken_hiddenimports
    + sfmpeg_hidden
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
        "static_ffmpeg",
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
