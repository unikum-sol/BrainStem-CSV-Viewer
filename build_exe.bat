@echo off
REM ============================================================
REM  BrainStem CSV Viewer - Windows EXE Build
REM  Kann per Doppelklick oder aus jedem Verzeichnis gestartet werden.
REM ============================================================
cd /d "%~dp0"

echo [1/3] Virtuelle Umgebung anlegen (falls noch nicht vorhanden)...
if not exist venv (
    python -m venv venv
)
REM Das Python der venv wird direkt aufgerufen statt ueber activate.bat:
REM activate.bat enthaelt den absoluten Pfad von der Erstellung und zeigt nach
REM einem Verschieben des Ordners ins Leere (dann wuerde ins System-Python
REM installiert).
set "VENV_PY=%~dp0venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
    echo venv\Scripts\python.exe fehlt. Ordner venv loeschen und neu starten.
    pause
    exit /b 1
)

echo [2/3] Abhaengigkeiten installieren...
"%VENV_PY%" -m pip install --upgrade pip
"%VENV_PY%" -m pip install -r requirements.txt pyinstaller

echo [3/3] EXE bauen (PyInstaller, onefile, windowed)...
"%VENV_PY%" -m PyInstaller --noconfirm --onefile --windowed --name BrainStemCSVViewer csv_viewer.py

echo.
echo Fertig. Die EXE liegt unter: dist\BrainStemCSVViewer.exe
pause
