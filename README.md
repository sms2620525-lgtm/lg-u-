# JARVIS Cyber · 우주 테마 보안 작업 공간

## 설치 / DMG

GitHub **Actions → Build macOS DMG → 성공한 실행 → Artifacts**에서 `JarvisCyber-ARM64` ZIP을 받아 안의 DMG를 엽니다. Apple Silicon 전용입니다. Intel 빌드는 더 이상 생성하지 않습니다. 앱을 Applications로 옮겨 실행하면 기본 브라우저에 로컬 화면이 열립니다. 이 빌드는 macOS 15 실행 환경에서 검증합니다.

DMG는 아직 Developer ID 서명/공증되지 않은 개발용 빌드입니다. macOS가 실행을 차단할 수 있습니다. 시스템 전체 보안 기능을 끄지 마세요.

Nmap은 포함하지 않습니다. [공식 Nmap macOS 설치 안내](https://nmap.org/book/inst-macosx.html)에 따라 별도 설치하세요. 앱은 `/opt/homebrew/bin/nmap`, `/usr/local/bin/nmap`, PATH를 확인합니다. Python은 DMG에 포함됩니다.

직접 실행하려면 Python 3.9 이상에서 `python3 app.py`. 직접 DMG를 만들려면 macOS에서 `bash build-macos.sh`.

## 현재 구현

- IP 하나 입력 → Nmap TCP 주요 100포트 / 가벼운 서비스 버전 탐지
- IPv4 / IPv6, 중단 버튼, 최대 실행 시간 150초
- macOS 터미널에 정확한 명령과 실시간 로그 표시 (Nmap은 앱에서 실행)
- 실제 Nmap XML 결과를 3D 포트 노드와 텍스트 목록으로 표시, 드래그 회전
- 지원 브라우저에서 IP 음성 입력 → 인식 결과 확인 → 점검 시작
- 맥 시스템 기본 TTS, 개인 기억 저장·삭제
- 앱 종료 버튼 (브라우저 탭을 닫는 것만으로 서버가 종료되지는 않음)

소유하거나 점검 권한이 있는 장치에 사용하세요. 열린 포트는 취약점 확정 판정이 아닙니다. 3D 배치는 포트 구성을 표현하며 실제 네트워크 경로나 지리 정보가 아닙니다. `-Pn`을 쓰므로 응답이 없는 주소도 점검하며 호스트 존재 여부를 확정하지 않습니다. 임의 셸 명령, exploit, 비밀번호 공격은 구현하지 않았습니다.

## 안드로이드 휴대폰으로 3D 회전

1. Actions → Build Android Remote → 성공한 실행 → Artifacts에서 `JarvisRemote-Android`를 받아 APK를 휴대폰에 설치합니다. 개인 테스트용 debug 서명 APK입니다.
2. 맥과 휴대폰을 같은 신뢰할 수 있는 Wi-Fi에 연결합니다.
3. 맥 앱에서 **휴대폰 연결 코드**를 누릅니다. 표시되는 맥 IP와 6자리 코드를 휴대폰 앱에 입력합니다.
4. 휴대폰에서 **맥에 연결**을 누르고 앱을 화면에 띄운 채 기울입니다. 맥의 **현재 자세를 중심으로** 버튼으로 기준 자세를 맞춥니다.
5. 사용 후 맥에서 **연결 끊기**를 누릅니다. macOS 방화벽이 묻는 경우 이 앱의 로컬 네트워크 수신이 필요합니다.

휴대폰 자체의 회전 센서를 사용합니다. 같은 Wi-Fi의 IPv4 사설 주소에서 동작하며 Bluetooth 연결이 아닙니다. 연결 중에만 8766 포트를 열고 자세 데이터만 받습니다. 기억 DB나 Nmap 실행 API는 이 포트에 노출하지 않습니다. 코드는 5분/5회 시도 제한, 세션은 1시간입니다. 기울기 데이터와 페어링은 로컬 HTTP로 전송되므로 공용 Wi-Fi에서는 사용하지 마세요. 앱을 배경으로 보내면 센서 전송이 멈춥니다. 센서 없는 기기는 지원하지 않습니다.

## 갤럭시 핏3 / 손목 제어

핏3 실기기 Bluetooth 센서 연동은 **미구현**입니다. 삼성 공식 제품 정보에는 가속도/자이로 센서와 FreeRTOS가 명시돼 있지만, 공개 Samsung Health Sensor SDK는 Wear OS 갤럭시 워치4 이상이 대상입니다. 핏3 원시 자세 데이터를 실시간으로 받는 공식 API는 확인되지 않았습니다. Bluetooth 페어링만으로 원시 센서 데이터가 제공되는 것은 아닙니다.

향후 검증된 센서 어댑터가 `window.jarvisOrientation({pitch, roll})`에 각도(degree)를 전달하면 화면을 회전시킬 수 있습니다. 이것은 화면 입력 인터페이스이며 워치 연결 구현이 아닙니다. 현재는 마우스 또는 연결된 안드로이드 휴대폰 자체 센서로 회전합니다.

- https://developer.samsung.com/health/sensor/faq.html
- https://www.samsung.com/uk/business/watches/galaxy-fit/galaxy-fit3-grey-bluetooth-sm-r390nzaaeub/

## 저장과 한계

맥에서는 `~/Library/Application Support/JarvisCyber/`에 기억 SQLite와 스캔 XML/로그가 저장됩니다. 기존 소스 실행 버전의 `data/jarvis.sqlite3`는 처음 실행 시 새 DB가 없을 때 복사합니다. 환경 변수 `JARVIS_DATA_DIR`로 경로를 지정할 수 있습니다. 개인 데이터는 GitHub로 전송하지 않습니다. 주 앱은 `127.0.0.1:8765`에서만 수신합니다. 휴대폰 연결을 켜면 별도 모션 수신기가 LAN의 8766 포트에서 수신합니다. TTS는 macOS `say`, 음성 인식은 브라우저 제공 기능이므로 브라우저에 따라 외부 음성 인식 서비스를 사용할 수 있습니다.

**GPT 대화/로그인, 외부 DB 동기화는 아직 구현되지 않았습니다.** 현재 보안 작업은 고정된 Nmap 명령을 실행하는 도구입니다. 다른 스캐너는 아직 포함하지 않습니다.

## 테스트

`python3 -m unittest discover -s tests`

명령 주입 입력 거부, 단일 IP 검증, XML 파싱, 기억 CRUD, CSRF 차단, 정적 파일을 검사합니다. GitHub macOS 빌드는 앱 실행/HTTP 응답과 DMG 무결성을 추가 검사합니다. 실제 맥 음성·터미널·마이크·핏3 동작은 별도 실기기 검증이 필요합니다.
