"""JARVIS local prototype. Python 3.9+, no extra dependencies."""
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import threading
import tempfile
import atexit
import urllib.parse
import webbrowser
from pathlib import Path

from http.server import BaseHTTPRequestHandler

from auth import Auth, AuthError, read_cookie, session_cookie_header, cleared_session_cookie_header
from voice import Voice
from chatgpt import ChatGPT, Conversation
from microphone import Microphone
from wake import WakeController
from security import Scanner
from phone import PhoneBridge, NumericHTTPServer
from cloud import Cloud, RuntimeAuth
from callback import callback_server

if getattr(sys, 'frozen', False):
    ROOT = Path(sys._MEIPASS)
else:
    ROOT = Path(__file__).resolve().parent

DATA = Path(os.environ.get('JARVIS_DATA_DIR', str(Path.home() / 'Library/Application Support/JarvisCyber' if sys.platform == 'darwin' else ROOT / 'data')))
DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
# The legacy store is retained solely for regression tests and explicit migration reads.
LOCAL_TEST = os.environ.get('JARVIS_TEST_LOCAL') == '1' and '--no-browser' in sys.argv
runtime = tempfile.TemporaryDirectory(prefix='jarvis-runtime-')
atexit.register(runtime.cleanup)
DB = DATA / 'jarvis.sqlite3'
TOKEN = secrets.token_urlsafe(32)
PORT = int(os.environ.get('JARVIS_PORT', '8765'))
ORIGIN = f'http://127.0.0.1:{PORT}'
cloud = None if LOCAL_TEST else Cloud()
scanner = Scanner(DATA / 'scans' if LOCAL_TEST else Path(runtime.name) / 'scans', cloud=cloud)
phone = PhoneBridge()
auth = Auth(DB) if LOCAL_TEST else RuntimeAuth()
voice = Voice(DATA, cloud=cloud)
native_window = None
quitting = threading.Event()
account = ChatGPT(DATA, ORIGIN + '/auth/callback', cloud=cloud)
microphone = Microphone(ROOT)

def connect():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

if LOCAL_TEST:
    with connect() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS memories (id INTEGER PRIMARY KEY, text TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
    os.chmod(DB, 0o600)
conversation = Conversation(account, connect, cloud=cloud)
wake = WakeController(microphone, voice, conversation, account)

def quit_app():
    quitting.set()
    wake.pause(disable=True)
    if native_window:
        native_window.destroy()

native_delegate = None

def install_native_delegate():
    # Preserve pywebview's delegate lifecycle, adding Dock reopen and real Cmd+Q.
    from webview.platforms.cocoa import BrowserView
    from AppKit import NSApplication
    from PyObjCTools import AppHelper
    from objc import super as objc_super
    class JarvisAppDelegate(BrowserView.AppDelegate):
        def applicationShouldHandleReopen_hasVisibleWindows_(self, app, visible):
            native_window.show()
            return True

        def applicationShouldTerminate_(self, app):
            quitting.set()
            wake.pause(disable=True)
            microphone.stop()
            voice.stop()
            return objc_super(JarvisAppDelegate, self).applicationShouldTerminate_(app)

    def install():
        global native_delegate
        native_delegate = JarvisAppDelegate.alloc().init()
        NSApplication.sharedApplication().setDelegate_(native_delegate)
    AppHelper.callAfter(install)

def hide_on_close():
    if not quitting.is_set():
        native_window.hide()
        return False
    return True


def migrate_legacy():
    """Explicit, repeatable import. Existing local originals are never deleted."""
    import uuid
    if not cloud:
        raise ValueError('클라우드 모드에서만 가져올 수 있어요.')
    conversation.cancel()
    counts = {'memories':0,'messages':0,'files':0}
    def ident(name):
        return str(uuid.uuid5(uuid.NAMESPACE_URL, 'jarvis-legacy:'+cloud.device+':'+name))
    if DB.exists():
        with sqlite3.connect(DB.as_uri()+'?mode=ro', uri=True) as db:
            db.row_factory = sqlite3.Row
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'memories' in tables:
                for row in db.execute('SELECT id,text FROM memories ORDER BY id'):
                    cloud.put('memory', {'text':row['text']}, ident('memory:'+str(row['id'])))
                    counts['memories'] += 1
            if 'chats' in tables:
                for row in db.execute('SELECT id,account,role,text FROM chats ORDER BY id'):
                    cloud.put('message', {'account':row['account'],'role':row['role'],'text':row['text']}, ident('chat:'+str(row['id'])))
                    counts['messages'] += 1
    for filename, key in [('voice.json','voice'),('chatgpt-accounts.json','chatgpt:'+cloud.device)]:
        path = DATA / filename
        if path.exists():
            value = json.loads(path.read_text())
            existing = cloud.setting(key)
            if existing is None or (filename.startswith('chatgpt') and not existing.get('accounts')):
                cloud.save_setting(key, value)
                if filename.startswith('chatgpt'):
                    account.loaded = False
    scan_dir = DATA / 'scans'
    if scan_dir.exists():
        for path in scan_dir.iterdir():
            if path.is_file() and path.suffix in ('.xml','.log') and path.stat().st_size <= 16777216:
                cloud.blob('legacy-scans/'+path.name,path.read_bytes())
                counts['files'] += 1
    return {'ok':True, **counts}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, value, content_type='application/json; charset=utf-8', headers=None):
        body = value.encode() if isinstance(value, str) else json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        for name, value_ in (headers or {}).items():
            self.send_header(name, value_)
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location):
        self.send_response(302)
        self.send_header('Location', location)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def is_authed(self):
        return auth.verify_session(read_cookie(self.headers.get('Cookie'), 'jarvis_session'))

    def page(self, name):
        return self.send(200, (ROOT / name).read_text().replace('__TOKEN__', TOKEN), 'text/html; charset=utf-8')

    def do_GET(self):
        try:
            self.get_request()
        except ValueError as e:
            self.send(503, {'error':str(e)})

    def get_request(self):
        if self.headers.get('Host') != f'127.0.0.1:{PORT}':
            return self.send(403, {'error': '잘못된 접근 주소입니다.'})

        if self.path.startswith('/auth/callback?'):
            try:
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if any(len(v) != 1 for v in parsed.values()):
                    raise ValueError('로그인 응답 형식이 올바르지 않아요.')
                account.complete({k: v[0] for k, v in parsed.items()})
                conversation.cancel()
                return self.send(200, 'ChatGPT 연결이 완료되었습니다. JarvisCyber 앱으로 돌아가세요.', 'text/plain; charset=utf-8')
            except ValueError as e:
                return self.send(400, str(e), 'text/plain; charset=utf-8')

        if self.path == '/setup':
            if auth.has_password():
                return self.redirect('/' if self.is_authed() else '/login')
            return self.page('setup.html')
        if self.path == '/login':
            if not auth.has_password():
                return self.redirect('/setup')
            if self.is_authed():
                return self.redirect('/')
            return self.page('cloud-login.html' if cloud else 'login.html')
        if self.path == '/':
            if not auth.has_password():
                return self.redirect('/setup')
            if not self.is_authed():
                return self.redirect('/login')
            return self.page('index.html')

        if self.path in ('/cyber.js', '/cyber.css', '/conversation.js', '/cloud-ui.js'):
            kind = 'application/javascript' if self.path.endswith('.js') else 'text/css'
            return self.send(200, (ROOT / self.path[1:]).read_text(), kind + '; charset=utf-8')

        if self.path == '/api/cloud/status':
            return self.send(200, cloud.status() if cloud else {'connected':False})

        if self.path.startswith('/api/'):
            if not self.is_authed():
                return self.send(401, {'error': '로그인이 필요합니다.'})
            if self.path == '/api/account':
                return self.send(200, account.public())
            if self.path == '/api/chat':
                return self.send(200, conversation.snapshot())
            if self.path == '/api/wake':
                return self.send(200, wake.snapshot())
            if self.path == '/api/microphone':
                return self.send(200, microphone.snapshot())
            if self.path == '/api/voice':
                return self.send(200, voice.snapshot())
            if self.path == '/api/phone':
                return self.send(200, phone.snapshot())
            if self.path == '/api/scan':
                result = scanner.snapshot()
                if cloud and result['status']=='idle':
                    rows = cloud.records('scan',limit=1)
                    if rows:
                        result = {**rows[0]['payload'], 'restored':True}
                return self.send(200, result)
            if self.path == '/api/memories':
                if cloud:
                    return self.send(200, {'memories':cloud.memories(), 'tts_available':sys.platform == 'darwin'})
                with connect() as conn:
                    rows = [dict(r) for r in conn.execute('SELECT * FROM memories ORDER BY id DESC')]
                return self.send(200, {'memories': rows, 'tts_available': sys.platform == 'darwin'})

        self.send(404, {'error': '찾을 수 없습니다.'})

    def do_POST(self):
        if (self.headers.get('Host') != f'127.0.0.1:{PORT}' or
                self.headers.get('Origin') != ORIGIN or
                self.headers.get('X-Jarvis-Token') != TOKEN):
            return self.send(403, {'error': '접근할 수 없습니다.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 20000:
                raise ValueError()
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError()

            if cloud and self.path in ('/api/cloud/otp','/api/cloud/verify','/api/cloud/resume'):
                if self.path.endswith('/otp'):
                    return self.send(200, cloud.otp(payload.get('email')))
                if self.path.endswith('/verify'):
                    wake.pause(disable=True)
                    conversation.cancel()
                    voice.stop()
                    cloud.verify(payload.get('code'))
                    account.loaded = False
                    account.meta = {'host':'urn:uuid:'+str(__import__('uuid').uuid4()),'active':None,'accounts':{}}
                    auth.sessions.clear()
                else:
                    cloud.resume()
                return self.send(200, {'ok':True}, headers={'Set-Cookie':session_cookie_header(auth.issue_session())})
            if cloud and self.path in ('/api/setup','/api/login'):
                raise ValueError('이메일 인증으로 클라우드에 로그인하세요.')

            if self.path == '/api/setup':
                if auth.has_password():
                    return self.send(400, {'error': '이미 비밀번호가 설정되어 있습니다.'})
                try:
                    auth.set_password(payload.get('password', ''))
                except AuthError as e:
                    return self.send(400, {'error': str(e)})
                token = auth.issue_session()
                return self.send(200, {'ok': True}, headers={'Set-Cookie': session_cookie_header(token)})
            elif self.path == '/api/login':
                try:
                    ok = auth.verify_password(payload.get('password', ''))
                except AuthError as e:
                    return self.send(429, {'error': str(e)})
                if not ok:
                    return self.send(401, {'error': '비밀번호가 올바르지 않습니다.'})
                token = auth.issue_session()
                return self.send(200, {'ok': True}, headers={'Set-Cookie': session_cookie_header(token)})
            elif self.path == '/api/logout':
                wake.pause(disable=True)
                microphone.stop()
                conversation.cancel()
                voice.stop()
                auth.revoke_session(read_cookie(self.headers.get('Cookie'), 'jarvis_session'))
                return self.send(200, {'ok': True}, headers={'Set-Cookie': cleared_session_cookie_header()})

            if not self.is_authed():
                return self.send(401, {'error': '로그인이 필요합니다.'})

            if self.path == '/api/cloud/logout':
                wake.pause(disable=True)
                microphone.stop()
                conversation.cancel()
                voice.stop()
                cloud.signout()
                auth.sessions.clear()
                account.loaded = False
                return self.send(200, {'ok':True}, headers={'Set-Cookie':cleared_session_cookie_header()})
            elif self.path == '/api/cloud/migrate':
                return self.send(200, migrate_legacy())
            elif self.path == '/api/account/login':
                return self.send(200, account.begin(payload.get('client')))
            elif self.path == '/api/account/models':
                return self.send(200, account.models())
            elif self.path == '/api/account/model':
                account.select_model(payload.get('model'))
            elif self.path == '/api/account/switch':
                wake.pause(disable=True)
                conversation.cancel()
                voice.stop()
                return self.send(200, account.switch(payload.get('client')))
            elif self.path == '/api/account/logout':
                wake.pause(disable=True)
                microphone.stop()
                conversation.cancel()
                voice.stop()
                return self.send(200, account.signout())
            elif self.path == '/api/account/usage':
                webbrowser.open('https://chatgpt.com/settings/usage')
            elif self.path == '/api/chat':
                wake.pause()
                microphone.stop()
                voice.stop()
                return self.send(200, conversation.start(payload.get('text')))
            elif self.path == '/api/chat/cancel':
                conversation.cancel()
                voice.stop()
            elif self.path == '/api/chat/clear':
                conversation.clear()
                voice.stop()
            elif self.path == '/api/wake/enable':
                return self.send(200, wake.enable())
            elif self.path == '/api/wake/disable':
                return self.send(200, wake.pause(disable=True))
            elif self.path == '/api/wake/pause':
                return self.send(200, wake.pause())
            elif self.path == '/api/wake/resume':
                return self.send(200, wake.resume())
            elif self.path == '/api/microphone/start':
                wake.pause()
                return self.send(200, microphone.start())
            elif self.path == '/api/microphone/stop':
                microphone.stop()
            elif self.path == '/api/voice':
                return self.send(200, voice.save(payload))
            elif self.path == '/api/voice/search':
                return self.send(200, voice.models(payload.get('query', 'Jarvis')))
            elif self.path == '/api/phone/enable':
                return self.send(200, phone.enable())
            elif self.path == '/api/phone/connect':
                return self.send(200, phone.connect(payload.get('device'), payload.get('pin')))
            elif self.path == '/api/phone/disable':
                phone.stop()
            elif self.path == '/api/scan':
                return self.send(200, scanner.start(payload.get('target'), payload.get('terminal') is True))
            elif self.path == '/api/scan/cancel':
                scanner.cancel()
            elif self.path == '/api/quit':
                scanner.cancel()
                quit_app()
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            elif self.path == '/api/memories':
                text = payload.get('text', '')
                if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
                    return self.send(400, {'error': '기억은 1~2000자로 입력하세요.'})
                if cloud:
                    cloud.put('memory', {'text':text.strip()})
                else:
                    with connect() as conn:
                        conn.execute('INSERT INTO memories(text) VALUES (?)', (text.strip(),))
            elif self.path == '/api/delete':
                if cloud:
                    cloud.delete('memory', record_id=payload.get('id'))
                else:
                    if type(payload.get('id')) is not int:
                        raise ValueError()
                    with connect() as conn:
                        conn.execute('DELETE FROM memories WHERE id = ?', (payload['id'],))
            elif self.path == '/api/speak':
                microphone.stop()
                return self.send(200, voice.speak(payload.get('text', '')))
            elif self.path == '/api/stop':
                voice.stop()
            else:
                return self.send(404, {'error': '찾을 수 없습니다.'})
            self.send(200, {'ok': True})
        except (ValueError, TypeError) as e:
            self.send(400, {'error': str(e) or '입력 형식을 확인하세요.'})
        except (OSError, sqlite3.Error, subprocess.SubprocessError):
            self.send(500, {'error': '처리하지 못했어요. 다시 시도해 주세요.'})

if __name__ == '__main__':
    if '--network-smoke' in sys.argv:
        import jwt
        from network import tls_context
        discovery = account.discover()
        jwt.PyJWKClient(discovery['jwks_uri'], ssl_context=tls_context()).get_jwk_set()
        sys.exit(0)
    server = NumericHTTPServer(('127.0.0.1', PORT), Handler)
    cloud_callback = None
    if cloud:
        try:
            cloud_callback = callback_server(cloud)
            threading.Thread(target=cloud_callback.serve_forever, daemon=True).start()
        except OSError:
            # The masked return-URL field remains available if another app owns port 3000.
            cloud.error = '다른 앱이 인증 복귀 포트를 사용 중이에요. 메일 인증 후 주소창의 복귀 주소를 아래 입력란에 붙여넣으세요.'
    try:
        if '--no-browser' in sys.argv:
            # Headless integration-test mode, never opens a browser.
            server.serve_forever()
        else:
            import webview
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            native_window = webview.create_window('JARVIS · Command Center', ORIGIN,
                width=1440, height=940, min_size=(1000, 720), background_color='#020c10')
            smoke = '--native-smoke' in sys.argv
            smoke_result = {'ok': False}
            native_window.events.closing += hide_on_close
            from webview.menu import Menu, MenuAction
            app_menu = [Menu('자비스', [MenuAction('창 열기', native_window.show),
                MenuAction('박수 대기 끄기', lambda: wake.pause(disable=True)),
                MenuAction('자비스 종료', quit_app)])]
            if smoke:
                subprocess.run([str(ROOT / 'JarvisSpeech'), '--check'], check=True, stdout=subprocess.DEVNULL, timeout=10)
                def check_window():
                    try:
                        smoke_result['ok'] = hide_on_close() is False
                        native_window.show()
                        smoke_result['ok'] = smoke_result['ok'] and bool(native_window.evaluate_js("document.querySelector('input[type=email]') !== null"))
                    finally:
                        quit_app()
                native_window.events.loaded += check_window
                watchdog = threading.Timer(40, quit_app)
                watchdog.daemon = True
                watchdog.start()
            webview.start(install_native_delegate, gui='cocoa', debug=False, private_mode=True, menu=app_menu)
            if smoke:
                watchdog.cancel()
                if not smoke_result['ok']:
                    raise RuntimeError('Native WebKit window did not load the setup page')
            server.shutdown()
            thread.join(timeout=5)
    except KeyboardInterrupt:
        pass
    finally:
        wake.pause(disable=True)
        microphone.stop()
        conversation.cancel()
        phone.stop()
        scanner.cancel()
        voice.stop()
        server.server_close()
        if cloud_callback:
            cloud_callback.shutdown()
            cloud_callback.server_close()
