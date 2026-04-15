@echo off
:: ============================================================
:: Build-Skript: MP4 Transkription → Windows EXE
:: Voraussetzung: Python 3.10+ muss installiert sein
:: Ausführen mit Doppelklick oder in der Eingabeaufforderung
:: ============================================================

setlocal EnableDelayedExpansion
title MP4 Transkription – EXE Build

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   MP4 Transkription – EXE wird gebaut   ║
echo  ╚══════════════════════════════════════════╝
echo.

:: Python prüfen
python --version >nul 2>&1
if errorlevel 1 (
    echo [FEHLER] Python nicht gefunden!
    echo Bitte Python 3.10+ von https://www.python.org installieren.
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('python --version') do echo Python gefunden: %%v

:: pip aktualisieren
echo.
echo [1/4] pip wird aktualisiert...
python -m pip install --upgrade pip --quiet

:: Abhängigkeiten installieren
echo.
echo [2/4] Abhängigkeiten werden installiert (kann einige Minuten dauern)...
python -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [FEHLER] Installation der Abhängigkeiten fehlgeschlagen!
    pause
    exit /b 1
)

python -m pip install pyinstaller --quiet
if errorlevel 1 (
    echo [FEHLER] PyInstaller-Installation fehlgeschlagen!
    pause
    exit /b 1
)

echo Alle Abhängigkeiten installiert.

:: Alte Build-Artefakte aufräumen
echo.
echo [3/4] Alte Build-Dateien werden entfernt...
if exist "dist\MP4-Transkription" rmdir /s /q "dist\MP4-Transkription"
if exist "build\MP4-Transkription" rmdir /s /q "build\MP4-Transkription"

:: EXE bauen
echo.
echo [4/4] EXE wird gebaut (dauert 2–5 Minuten)...
pyinstaller transcribe_gui.spec --noconfirm
if errorlevel 1 (
    echo.
    echo [FEHLER] Build fehlgeschlagen! Siehe Ausgabe oben.
    pause
    exit /b 1
)

echo.
echo  ╔══════════════════════════════════════════╗
echo  ║   Build erfolgreich abgeschlossen!      ║
echo  ╚══════════════════════════════════════════╝
echo.
echo Die EXE befindet sich in:
echo   dist\MP4-Transkription\MP4-Transkription.exe
echo.
echo Hinweis: Den gesamten Ordner dist\MP4-Transkription\ weitergeben,
echo          nicht nur die .exe-Datei!
echo.
echo Soll der Ausgabeordner jetzt geöffnet werden? (J/N)
set /p OPEN=
if /i "!OPEN!"=="J" explorer "dist\MP4-Transkription"

pause
