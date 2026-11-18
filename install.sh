#!/bin/bash
# ORBIT telepítése erre a Macre. A futtatáshoz: ./install.sh
set -euo pipefail
cd "$(dirname "$0")"
UPDATE=0; [ "${1:-}" = "--update" ] && UPDATE=1
export ORBIT_CHECKOUT="$(pwd)"
[ -f UPDATE_SOURCE ] && export ORBIT_UPDATE_SOURCE="$(head -n1 UPDATE_SOURCE | tr -d ' \r\n')"
echo "▸ ORBIT telepítése…"

major=$(sw_vers -productVersion | cut -d. -f1)
if [ "$major" -lt 14 ]; then echo "Az ORBIT-hoz macOS 14 (Sonoma) vagy újabb kell."; exit 1; fi

if ! xcode-select -p >/dev/null 2>&1; then
  xcode-select --install || true
  echo "Telepítsd az Apple ingyenes Command Line Tools csomagját a felugró ablakban, majd futtasd újra: ./install.sh"
  exit 1
fi

echo "▸ Videós futtatókörnyezet (Clip Farm, Élő adás figyelő): ellenőrzés / telepítés…"
./setup_media.sh || echo "ℹ︎ A videós rész nem készült el (lásd fent). Az ORBIT többi funkciója működik; a videógyártáshoz később futtasd: ./setup_media.sh"

echo "▸ Az alkalmazás fordítása ezen a gépen (1-2 perc)…"
mkdir -p orbit_app/runtime
/usr/bin/swiftc -D ORBIT_APP -parse-as-library \
  trading_lab/ReszvenyAI.swift trading_lab/Dashboard.swift orbit_app/OrbitApp.swift orbit_app/OrbitMedia.swift \
  -o orbit_app/runtime/Orbit \
  -framework SwiftUI -framework AppKit -framework WebKit -framework Charts -framework UniformTypeIdentifiers -framework PDFKit
[ -f orbit_app/assets/Orbit.icns ] && cp orbit_app/assets/Orbit.icns orbit_app/runtime/Orbit.icns

echo "▸ Telepítés: /Applications/ORBIT.app, adatok: ~/Library/Application Support/Orbit"
/usr/bin/python3 orbit_app/install.py

if [ ! -d /Applications/Ollama.app ] && [ ! -d "$HOME/Applications/Ollama.app" ]; then
  echo "ℹ︎ A helyi AI-hoz az ingyenes Ollama kell: https://ollama.com/download (az ORBIT első indításkor is szól)."
fi

echo "✓ Kész."
if [ "$UPDATE" = "1" ]; then echo "Zárd be és nyisd meg újra az ORBIT-ot (Cmd+Q), hogy az új felület betöltődjön."; else echo "Az ORBIT most elindul."; open /Applications/ORBIT.app; fi
