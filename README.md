## Email login return fix (2026-10-04)

Email verification now uses PKCE. Keep JARVIS running and open the newest email
on the same Mac. Clicking its login button returns to the project's configured
`http://localhost:3000` address. A loopback-only listener exchanges the one-time
code with the in-memory verifier; the native app detects completion and opens.
If port 3000 belongs to another app, copy the post-verification return URL into
JARVIS's masked fallback field. Never send this URL to another person.
Restarting JARVIS loses pending proof; request a fresh email after restarting.
The app displays resend cooldowns, used/expired-link errors and server mail limits.
No server rate limits or email-verification protections have been disabled.

## Supabase cloud build (2026-10-04)

Normal launches use Supabase project `xflhofkqakxhagtbwycp` for conversations,
memories, settings, completed scan records, scan logs/XML and generated TTS cache.
The shipped key is publishable only; Row Level Security isolates each user.

1. Open the Apple Silicon app and request a login email using the Supabase project
   owner's email. The default Supabase mail service restricts recipients and rate limits.
2. Open the newest **Sign in / Confirm** link on the same Mac while the app is running.
   The app connects automatically. Numeric OTPs also work if custom SMTP/templates are configured.
3. Use **Continue with ChatGPT** separately to authorize GPT inference.
4. Import the Fish Audio key into Keychain. Choose **기존 로컬 데이터 가져오기** once
   to copy older memories, conversations, voice/account settings and scan files.
   Repeating the import uses stable IDs. Original local files are retained, not deleted.

The app stores cloud and provider credentials in macOS Keychain. Operational state
and brief read caches are in RAM. Nmap and afplay require temporary working files;
these are removed on normal exit (audio on playback completion). A crash may leave
OS temporary files. The app does not promise zero disk writes by macOS/WebKit.
Internet access is required; failed writes produce an error instead of silently
falling back to local persistence. Cloud logout revokes this session. Switching
storage accounts requires restarting the app to isolate active workers.

Applied database schema: `supabase/schema.sql`. A schema exists only once; do not
rerun CREATE statements on an already configured project. The old SQLite code is
retained for migration and explicit headless regression testing only.

Validation: `python -m unittest discover -s tests`, `python tests/integration.py`,
`python tests/cloud_smoke.py`. CI also checks the packaged native window, HTTPS and DMG.
Bluetooth motion, physical microphone access, and the user's ChatGPT plan login
still require a real Mac/device check. The app is ad-hoc signed, not notarized.

---

# JARVIS Cyber · 우주 테마 보안 작업 공간

## 설치 / DMG

GitHub **Actions → Build macOS DMG → 성공한 실행 → Artifacts**에서 `JarvisCyber-ARM64` ZIP을 받아 안의 DMG를 엽니다. Apple Silicon 전용입니다. Intel 빌드는 더 이상 생성하지 않습니다. 앱을 Applications로 옮겨 실행하면 전용 macOS 앱 창에서 화면이 열립니다. 외부 브라우저를 실행하지 않습니다. 이 빌드는 macOS 15 실행 환경에서 검증합니다.

DMG는 아직 Developer ID 서명/공증되지 않은 개발용 빌드입니다. macOS가 실행을 차단할 수 있습니다. 시스템 전체 보안 기능을 끄지 마세요.

Nmap은 포함하지 않습니다. [공식 Nmap macOS 설치 안내](https://nmap.org/book/inst-macosx.html)에 따라 별도 설치하세요. 앱은 `/opt/homebrew/bin/nmap`, `/usr/local/bin/nmap`, PATH를 확인합니다. Python은 DMG에 포함됩니다.

직접 실행하려면 Python 3.10 이상에서 `python3 -m pip install bleak==3.0.1 pywebview==6.2.1 keyring==25.7.0` 후 `python3 app.py`. 직접 DMG를 만들려면 macOS에서 `bash build-macos.sh`.

## 현재 구현

- IP 하나 입력 → Nmap TCP 주요 100포트 / 가벼운 서비스 버전 탐지
- IPv4 / IPv6, 중단 버튼, 최대 실행 시간 150초
- macOS 터미널에 정확한 명령과 실시간 로그 표시 (Nmap은 앱에서 실행)
- 실제 Nmap XML 결과를 3D 포트 노드와 텍스트 목록으로 표시, 드래그 회전
- WebKit이 지원하는 환경에서 IP 음성 입력 → 인식 결과 확인 → 점검 시작
- Fish Audio TTS, 개인 기억 저장·삭제
- 빨간 닫기 버튼은 창만 숨깁니다. Dock 아이콘 또는 자비스 메뉴에서 다시 열 수 있습니다. Cmd+Q / 자비스 종료로 서버와 Bluetooth·음성 재생을 종료합니다.

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

맥에서는 `~/Library/Application Support/JarvisCyber/`에 기억 SQLite와 스캔 XML/로그가 저장됩니다. 기존 소스 실행 버전의 `data/jarvis.sqlite3`는 처음 실행 시 새 DB가 없을 때 복사합니다. 환경 변수 `JARVIS_DATA_DIR`로 경로를 지정할 수 있습니다. 개인 데이터는 GitHub로 전송하지 않습니다. 주 앱은 `127.0.0.1:8765`에서만 수신합니다. 휴대폰 자세 데이터는 BLE로만 받으며 LAN 수신 포트는 열지 않습니다. TTS는 Fish Audio API이며 문장이 해당 서비스로 전송됩니다. 음성 인식은 내장 WebKit 지원 여부에 따라 제한될 수 있습니다.

**외부 DB 동기화는 아직 구현되지 않았습니다.** GPT 대화는 공식 Sign in with ChatGPT와 Responses API를 사용합니다. 대화 모델에는 터미널 실행 도구를 연결하지 않았으며, Nmap은 대시보드에서 사용자가 시작합니다.

## 테스트

`python3 -m unittest discover -s tests`

명령 주입 입력 거부, 단일 IP 검증, XML 파싱, 기억 CRUD, CSRF 차단, 정적 파일을 검사합니다. GitHub macOS 빌드는 앱 실행/HTTP 응답과 DMG 무결성을 추가 검사합니다. 실제 맥 음성·터미널·마이크·핏3 동작은 별도 실기기 검증이 필요합니다.

## Fish Audio 음성 설정

앱의 VOICE LINK에서 **API 키 파일 가져오기**로 키 하나가 든 RTF 또는 TXT 파일을 선택하세요. 키는 macOS Keychain에만 저장하며 GitHub, DMG, 설정 JSON에는 포함하지 않습니다. 음성 검색 결과에서 이름과 제작자를 확인하거나 Fish Audio 음성 페이지의 32자리 모델 ID를 입력하고 저장하세요. 기본 음성은 사용자가 지정한 Jarvis (MCU) J.A.R.V.I.S. (`612b878b113047d9a770c069c8b4fdfe`)입니다.

기본 엔진은 `s2.1-pro-free`이며 계정에 맞게 변경할 수 있습니다. 음성 테스트는 Fish Audio 요청을 수행합니다. 네트워크 오류, 키 오류, 잔액/요금제 오류는 앱 안에 표시됩니다. 정지 버튼은 생성 중 응답도 무효화하며 이전 음성이 뒤늦게 재생되지 않습니다.

사진의 청록색 원형 HUD를 코드로 구성했습니다. 회전 링, 빛나는 코어, 포트 노드가 휴대폰 자세에 함께 반응합니다. 코어는 스타일 표현이며 시스템 부하나 보안 탐지 값을 가장하지 않습니다.

## 대화 모드 / Ctrl+M

기본 화면은 대화 모드입니다. 앱 창에서 **Ctrl+M**으로 보안 대시보드를 열고 닫습니다. macOS의 Cmd+M(최소화)과 다른 단축키이며 앱 밖의 전역 단축키는 아닙니다.

1. **Continue with ChatGPT**를 누르고 공식 브라우저 인증 화면에서 계정과 앱의 요금제 사용 권한을 승인합니다. 인증할 때만 브라우저를 사용하고 실제 대화는 앱 안에서 진행됩니다.
2. 계정에서 제공하는 모델 목록을 불러옵니다. 모델을 선택하고 글로 대화하거나 **지금 말하기**를 누르세요.
3. **호출 대기 켜기**를 누르고 macOS 마이크·음성 인식 권한을 허용하세요. 박수를 두 번 치면 “네, 듣고 있어요”라고 말한 뒤 질문을 듣습니다. 답변 재생 후 약 20초 동안 후속 질문을 기다리고, 조용하면 박수 대기로 돌아갑니다. 창을 닫아도 Python 백그라운드 처리로 대화가 이어집니다. 대기는 앱 실행마다 직접 켜며, 대기 중에는 로컬에서 소리의 짧은 피크만 분석하고 녹음을 저장하거나 전송하지 않습니다. 비슷한 충격음에 반응할 수 있습니다.
4. 응답은 앱에 표시되며 Fish Audio로 읽습니다. 재생 중에는 마이크 인식을 멈춰 자기 목소리를 다시 입력하지 않습니다. **응답 중지**로 생성·재생을 중단합니다.

음성 인식은 Apple Speech를 사용하며 지원되는 한국어 온디바이스 모델이 있으면 우선 사용합니다. 환경에 따라 Apple 서버·인터넷 연결이 필요합니다. 앱이 종료되면 호출 감지도 종료됩니다. 잠자기 상태에서 깨우는 기능이나 운영체제 전체 상시 대기는 아닙니다. 실기기 마이크 품질과 Bluetooth는 별도 확인이 필요합니다.

ChatGPT 자격 증명은 키체인에, 계정 메타데이터는 Supabase에, 기기 식별자는 키체인에 저장합니다. state·PKCE·nonce와 ID 토큰 서명/issuer/audience/만료를 검사합니다. 계정별 대화는 Supabase에 분리 저장합니다. 기존 ChatGPT 웹 대화는 가져오지 않습니다. 최근 대화와 저장한 기억을 OpenAI에 전달하며, 읽을 답변은 Fish Audio에 전달합니다. ChatGPT 설정의 **사용량 관리**에서 앱 권한과 요금제 사용량을 확인할 수 있습니다. 계정/요금제의 지원 여부에 따라 로그인이 되더라도 추론 권한이 없을 수 있습니다.

검증: OAuth 보안/갱신과 스트리밍 성공·실패는 모의 서버 응답으로 테스트합니다. 실제 사용자 ChatGPT 로그인·사용 권한 승인·마이크 입력은 설치 후 본인이 완료해야 합니다.

## OpenRouter · 말투 선택

대화 화면의 **AI 연결 · 말투 설정**에서 ChatGPT 또는 OpenRouter를 선택합니다. OpenRouter를 선택한 뒤 API 키를 입력하고 **키 확인 · 저장**을 누르세요. `/key`로 키를 확인하며 검증 과정에서 유료 답변을 생성하지 않습니다. 모델 목록은 OpenRouter `/models`에서 가져오고, 텍스트 대화 모델을 이름·ID로 검색한 뒤 대화 입력창의 모델 목록에서 직접 선택합니다. 표시 가격은 목록의 100만 토큰당 입력/출력 가격이며 추가 과금 항목은 포함하지 않습니다. OpenRouter 사용료는 ChatGPT 구독과 별도입니다.

기본 말투는 차분하고 간결한 자비스 존댓말이며, 친근한 반말 / 정중하고 상세한 말투로 바꿀 수 있습니다. 말투는 다음 응답과 박수 호출 인사부터 적용됩니다. Fish Audio 목소리 모델 자체는 바뀌지 않습니다. OpenRouter도 기존 음성 입력·답변 읽기·창을 닫은 상태의 박수 대기를 사용합니다. 서비스·모델·키·말투 변경 시 진행 중 응답과 대기를 중단하므로 호출 대기는 다시 켜 주세요.

선택한 서비스·모델·말투는 기존 사용자별 Supabase settings 레코드에 저장합니다. API 키는 사용자 ID별 macOS Keychain에만 저장하며 앱 화면이나 저장소로 반환하지 않습니다. ChatGPT 대화와 OpenRouter 대화는 별도로 저장합니다. OpenRouter를 선택하면 질문·최근 대화·기억은 OpenRouter 및 해당 모델 제공자에게 전달됩니다.

검증: 모델 목록 실응답 구조 확인, 모의 스트림 성공/실패 및 키 검증/삭제/계정 격리 테스트. 실제 사용자 키로 유료 추론을 호출하는 검증은 하지 않습니다.

참고: https://openrouter.ai/docs/api_reference/streaming · https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties
