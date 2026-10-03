#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ "$(uname -s)" != Darwin ]; then
  echo 'macOS에서 실행해야 DMG를 만들 수 있습니다.' >&2
  exit 1
fi
python3 -m venv .build-venv
.build-venv/bin/python -m pip install 'pyinstaller==6.22.2'
.build-venv/bin/python -m PyInstaller --noconfirm --clean --windowed --name JarvisCyber --add-data 'index.html:.' --add-data 'cyber.js:.' --add-data 'cyber.css:.' app.py
mkdir -p dist/dmg-stage
cp -R dist/JarvisCyber.app dist/dmg-stage/
ln -s /Applications dist/dmg-stage/Applications
hdiutil create -volname JarvisCyber -srcfolder dist/dmg-stage -ov -format UDZO "dist/JarvisCyber-$(uname -m).dmg"
