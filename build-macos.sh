#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ "$(uname -s)" != Darwin ]; then
  echo 'macOS에서 실행해야 DMG를 만들 수 있습니다.' >&2
  exit 1
fi
python3 -m venv .build-venv
.build-venv/bin/python -m pip install 'pyinstaller==6.22.2' 'bleak==3.0.1' 'pywebview==6.2.1' 'keyring==25.7.0' 'PyJWT[crypto]==2.10.1' 'certifi==2026.7.22'
mkdir -p build
.build-venv/bin/python - <<'SPEECHPLIST'
import plistlib
from pathlib import Path
p=Path('build/speech-info.plist')
p.write_bytes(plistlib.dumps({'CFBundleIdentifier':'space.jarvis.cyber.speech','CFBundleName':'JarvisCyber Voice','NSMicrophoneUsageDescription':'자비스 호출과 음성 대화에 마이크를 사용합니다.','NSSpeechRecognitionUsageDescription':'한국어 음성을 텍스트로 변환해 자비스와 대화합니다.'}))
SPEECHPLIST
cp native/SpeechHelper.swift build/main.swift
xcrun swiftc build/main.swift native/ClapDetector.swift -o build/JarvisSpeech -framework AVFoundation -framework Speech \
  -Xlinker -sectcreate -Xlinker __TEXT -Xlinker __info_plist -Xlinker build/speech-info.plist
build/JarvisSpeech --check
build/JarvisSpeech --clap-check
.build-venv/bin/python -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --collect-submodules bleak \
  --collect-all webview \
  --hidden-import=webview.platforms.cocoa \
  --hidden-import=keyring.backends.macOS \
  --hidden-import=voice \
  --hidden-import=chatgpt \
  --hidden-import=microphone \
  --hidden-import=jwt \
  --hidden-import=network \
  --hidden-import=cloud \
  --hidden-import=callback \
  --add-data 'cloud-login.html:.' \
  --add-data 'cloud-ui.js:.' \
  --collect-data certifi \
  --collect-all cryptography \
  --add-binary 'build/JarvisSpeech:.' \
  --add-data 'conversation.js:.' \
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
data['NSMicrophoneUsageDescription']='소리 감지와 IP 음성 입력에 마이크를 사용합니다.'
data['NSSpeechRecognitionUsageDescription']='IP 주소를 음성으로 입력합니다.'
data['CFBundleIdentifier']='space.jarvis.cyber'
with p.open('wb') as f: plistlib.dump(data,f)
PLIST
codesign --force --deep --sign - dist/JarvisCyber.app
stage=$(mktemp -d "${TMPDIR:-/tmp}/jarvis-dmg.XXXXXX")
trap 'rm -rf "$stage"' EXIT
cp -R dist/JarvisCyber.app "$stage/"
ln -s /Applications "$stage/Applications"
hdiutil create -volname JarvisCyber -srcfolder "$stage" -ov -format UDZO "dist/JarvisCyber-$(uname -m).dmg"
