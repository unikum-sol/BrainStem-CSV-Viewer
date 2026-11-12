#!/usr/bin/env bash
# ============================================================
#  BrainStem CSV Viewer - Linux Build (native Binary)
#  Muss auf einem echten Linux-Rechner ausgefuehrt werden.
#  PyInstaller kann nicht cross-kompilieren: eine unter Windows
#  gebaute EXE laeuft nicht unter Linux und umgekehrt.
# ============================================================
set -e
cd "$(dirname "$0")"

echo "[1/3] Virtuelle Umgebung anlegen (falls noch nicht vorhanden)..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
# Python der venv direkt verwenden (activate enthaelt den absoluten Pfad
# von der Erstellung und passt nach einem Verschieben nicht mehr).
VENV_PY="venv/bin/python"

echo "[2/3] Abhaengigkeiten installieren..."
"$VENV_PY" -m pip install --upgrade pip
"$VENV_PY" -m pip install -r requirements.txt pyinstaller

echo "[3/3] Binary bauen (PyInstaller, onefile)..."
"$VENV_PY" -m PyInstaller --noconfirm --onefile --windowed --name BrainStemCSVViewer csv_viewer.py

echo
echo "Fertig. Binary liegt unter: dist/BrainStemCSVViewer"
echo "Direkt starten ohne Build: python3 csv_viewer.py"
