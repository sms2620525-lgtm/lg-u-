#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ "$(uname -s)" != Darwin ]; then
  echo 'macOS에서 실행해야 DMG를 만들 수 있습니다.' >&2
  exit 1
fi
python3 -m venv .build-venv
.build-venv/bin/python -m pip install 'pyinstaller==6.22.2' 'bleak==3.0.1'
.build-venv/bin/python -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --collect-submodules bleak \
  --hidden-import=auth \
  --hidden-import=security \
  --hidden-import=phone \
  --name JarvisCyber \
  --add-data 'index.html:.' \
  --add-data 'setup.html:.' \
  --add-data 'login.html:.' \
  --add-data 'cyber.js:.' \
  --add-data 'cyber.css:.' \
  app.py
.build-venv/bin/python - <<'PLIST'
import plistlib
from pathlib import Path
p=Path('dist/JarvisCyber.app/Contents/Info.plist')
with p.open('rb') as f: data=plistlib.load(f)
data['NSBluetoothAlwaysUsageDescription']='휴대폰의 기울기를 Bluetooth로 받아 3D 화면을 회전합니다.'
data['CFBundleIdentifier']='space.jarvis.cyber'
with p.open('wb') as f: plistlib.dump(data,f)
PLIST
codesign --force --deep --sign - dist/JarvisCyber.app
stage=$(mktemp -d "${TMPDIR:-/tmp}/jarvis-dmg.XXXXXX")
trap 'rm -rf "$stage"' EXIT
cp -R dist/JarvisCyber.app "$stage/"
ln -s /Applications "$stage/Applications"
hdiutil create -volname JarvisCyber -srcfolder "$stage" -ov -format UDZO "dist/JarvisCyber-$(uname -m).dmg"
