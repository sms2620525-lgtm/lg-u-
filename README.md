# JARVIS Cyber · 우주 테마 보안 작업 공간

## 설치 / DMG

GitHub **Actions → Build macOS DMG → 성공한 실행 → Artifacts**에서 `JarvisCyber-ARM64` ZIP을 받아 안의 DMG를 엽니다. Apple Silicon 전용입니다. Intel 빌드는 더 이상 생성하지 않습니다. 앱을 Applications로 옮겨 실행하면 기본 브라우저에 로컬 화면이 열립니다. 이 빌드는 macOS 15 실행 환경에서 검증합니다.

DMG는 아직 Developer ID 서명/공증되지 않은 개발용 빌드입니다. macOS가 실행을 차단할 수 있습니다. 시스템 전체 보안 기능을 끄지 마세요.

Nmap은 포함하지 않습니다. [공식 Nmap macOS 설치 안내](https://nmap.org/book/inst-macosx.html)에 따라 별도 설치하세요. 앱은 `/opt/homebrew/bin/nmap`, `/usr/local/bin/nmap`, PATH를 확인합니다. Python은 DMG에 포함됩니다.

직접 실행하려면 Python 3.10 이상에서 `python3 app.py`. 직접 DMG를 만들려면 macOS에서 `bash build-macos.sh`.

## 현재 구현

- IP 하나 입력 → Nmap TCP 주요 100포트 / 가벼운 서비스 버전 탐지
- IPv4 / IPv6, 중단 버튼, 최대 실행 시간 150초
- macOS 터미널에 정확한 명령과 실시간 로그 표시 (Nmap은 앱에서 실행)
- 실제 Nmap XML 결과를 3D 포트 노드와 텍스트 목록으로 표시, 드래그 회전
- 지원 브라우저에서 IP 음성 입력 → 인식 결과 확인 → 점검 시작
- 맥 시스템 기본 TTS, 개인 기억 저장·삭제
- 앱 종료 버튼 (브라우저 탭을 닫는 것만으로 서버가 종료되지는 않음)

소유하거나 점검 권한이 있는 장치에 사용하세요. 열린 포트는 취약점 확정 판정이 아닙니다. 3D 배치는 포트 구성을 표현하며 실제 네트워크 경로나 지리 정보가 아닙니다. `-Pn`을 쓰므로 응답이 없는 주소도 점검하며 호스트 존재 여부를 확정하지 않습니다. 임의 셸 명령, exploit, 비밀번호 공격은 구현하지 않았습니다.

## 안드로이드 휴대폰을 Bluetooth 컨트롤러로 사용

1. `JarvisRemote-Android` APK를 휴대폰에 설치합니다. 개인 테스트용 debug 서명 APK입니다.
2. 맥과 휴대폰의 Bluetooth를 켭니다. 앱의 Bluetooth/주변 기기 권한을 허용합니다.
3. 휴대폰의 **Bluetooth 전송 시작**을 누릅니다. 6자리 코드가 표시됩니다.
4. 맥 앱의 **Bluetooth 휴대폰 검색** → 목록에서 휴대폰 선택 → 코드 입력 → **연결**.
5. 휴대폰을 기울이면 맥 3D 화면이 회전합니다. 맥의 **현재 자세를 중심으로** 버튼으로 기준을 맞춥니다.
6. 휴대폰 앱은 화면에 띄워 둡니다. 화면을 끄거나 앱을 벗어나면 전송이 중단됩니다.

Wi-Fi/인터넷 연결은 필요하지 않습니다. 시스템 Bluetooth 설정에서 수동 페어링하는 방식이 아니라 앱 내부에서 BLE 서비스에 연결합니다. 휴대폰은 BLE 광고와 회전 센서를 지원해야 합니다. 코드는 5분/5회 시도 제한이며, 앱에서 새 전송을 시작하면 새 코드가 발급됩니다. 전달 데이터는 초당 최대 20회 pitch/roll 두 각도이며 다른 폰 데이터는 수집하지 않습니다. BLE 실기기 통신은 CI에서 검증할 수 없으므로 실제 맥과 폰에서 확인해야 합니다.

소스에서 실행하려면 `python3 -m pip install bleak==3.0.1`이 필요합니다. DMG에는 포함되어 있습니다. 맥의 Bluetooth 권한을 거절했다면 시스템 설정 → 개인정보 보호 및 보안 → Bluetooth에서 허용하세요.

## 갤럭시 핏3 / 손목 제어

핏3 실기기 Bluetooth 센서 연동은 **미구현**입니다. 삼성 공식 제품 정보에는 가속도/자이로 센서와 FreeRTOS가 명시돼 있지만, 공개 Samsung Health Sensor SDK는 Wear OS 갤럭시 워치4 이상이 대상입니다. 핏3 원시 자세 데이터를 실시간으로 받는 공식 API는 확인되지 않았습니다. Bluetooth 페어링만으로 원시 센서 데이터가 제공되는 것은 아닙니다.

향후 검증된 센서 어댑터가 `window.jarvisOrientation({pitch, roll})`에 각도(degree)를 전달하면 화면을 회전시킬 수 있습니다. 이것은 화면 입력 인터페이스이며 워치 연결 구현이 아닙니다. 현재는 마우스 또는 연결된 안드로이드 휴대폰 자체 센서로 회전합니다.

- https://developer.samsung.com/health/sensor/faq.html
- https://www.samsung.com/uk/business/watches/galaxy-fit/galaxy-fit3-grey-bluetooth-sm-r390nzaaeub/

## 저장과 한계

맥에서는 `~/Library/Application Support/JarvisCyber/`에 기억 SQLite와 스캔 XML/로그가 저장됩니다. 기존 소스 실행 버전의 `data/jarvis.sqlite3`는 처음 실행 시 새 DB가 없을 때 복사합니다. 환경 변수 `JARVIS_DATA_DIR`로 경로를 지정할 수 있습니다. 개인 데이터는 GitHub로 전송하지 않습니다. 주 앱은 `127.0.0.1:8765`에서만 수신합니다. 휴대폰 자세 데이터는 BLE로만 받으며 LAN 수신 포트는 열지 않습니다. TTS는 macOS `say`, 음성 인식은 브라우저 제공 기능이므로 브라우저에 따라 외부 음성 인식 서비스를 사용할 수 있습니다.

**GPT 대화/로그인, 외부 DB 동기화는 아직 구현되지 않았습니다.** 현재 보안 작업은 고정된 Nmap 명령을 실행하는 도구입니다. 다른 스캐너는 아직 포함하지 않습니다.

## 테스트

`python3 -m unittest discover -s tests`

명령 주입 입력 거부, 단일 IP 검증, XML 파싱, 기억 CRUD, CSRF 차단, 정적 파일을 검사합니다. GitHub macOS 빌드는 앱 실행/HTTP 응답과 DMG 무결성을 추가 검사합니다. 실제 맥 음성·터미널·마이크·핏3 동작은 별도 실기기 검증이 필요합니다.
