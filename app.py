"""JARVIS local prototype. Python 3.9+, no extra dependencies."""
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path

from http.server import BaseHTTPRequestHandler

from auth import Auth, AuthError, read_cookie, session_cookie_header, cleared_session_cookie_header
from voice import Voice
from chatgpt import ChatGPT, Conversation
from microphone import Microphone
from security import Scanner
from phone import PhoneBridge, NumericHTTPServer

if getattr(sys, 'frozen', False):
    ROOT = Path(sys._MEIPASS)
else:
    ROOT = Path(__file__).resolve().parent

DATA = Path(os.environ.get('JARVIS_DATA_DIR', str(Path.home() / 'Library/Application Support/JarvisCyber' if sys.platform == 'darwin' else ROOT / 'data')))
DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
DB = DATA / 'jarvis.sqlite3'
legacy_db = ROOT / 'data' / 'jarvis.sqlite3'
if not DB.exists() and legacy_db.exists() and legacy_db != DB:
    with sqlite3.connect(legacy_db) as old, sqlite3.connect(DB) as new:
        old.backup(new)
TOKEN = secrets.token_urlsafe(32)
PORT = int(os.environ.get('JARVIS_PORT', '8765'))
ORIGIN = f'http://127.0.0.1:{PORT}'
scanner = Scanner(DATA / 'scans')
phone = PhoneBridge()
auth = Auth(DB)
voice = Voice(DATA)
native_window = None
account = ChatGPT(DATA, ORIGIN + '/auth/callback')
microphone = Microphone(ROOT)

def connect():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

with connect() as conn:
    conn.execute('CREATE TABLE IF NOT EXISTS memories (id INTEGER PRIMARY KEY, text TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
os.chmod(DB, 0o600)
conversation = Conversation(account, connect)

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
            return self.page('login.html')
        if self.path == '/':
            if not auth.has_password():
                return self.redirect('/setup')
            if not self.is_authed():
                return self.redirect('/login')
            return self.page('index.html')

        if self.path in ('/cyber.js', '/cyber.css', '/conversation.js'):
            kind = 'application/javascript' if self.path.endswith('.js') else 'text/css'
            return self.send(200, (ROOT / self.path[1:]).read_text(), kind + '; charset=utf-8')

        if self.path.startswith('/api/'):
            if not self.is_authed():
                return self.send(401, {'error': '로그인이 필요합니다.'})
            if self.path == '/api/account':
                return self.send(200, account.public())
            if self.path == '/api/chat':
                return self.send(200, conversation.snapshot())
            if self.path == '/api/microphone':
                return self.send(200, microphone.snapshot())
            if self.path == '/api/voice':
                return self.send(200, voice.snapshot())
            if self.path == '/api/phone':
                return self.send(200, phone.snapshot())
            if self.path == '/api/scan':
                return self.send(200, scanner.snapshot())
            if self.path == '/api/memories':
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
                microphone.stop()
                conversation.cancel()
                voice.stop()
                auth.revoke_session(read_cookie(self.headers.get('Cookie'), 'jarvis_session'))
                return self.send(200, {'ok': True}, headers={'Set-Cookie': cleared_session_cookie_header()})

            if not self.is_authed():
                return self.send(401, {'error': '로그인이 필요합니다.'})

            if self.path == '/api/account/login':
                return self.send(200, account.begin(payload.get('client')))
            elif self.path == '/api/account/models':
                return self.send(200, account.models())
            elif self.path == '/api/account/model':
                account.select_model(payload.get('model'))
            elif self.path == '/api/account/switch':
                conversation.cancel()
                voice.stop()
                return self.send(200, account.switch(payload.get('client')))
            elif self.path == '/api/account/logout':
                microphone.stop()
                conversation.cancel()
                voice.stop()
                return self.send(200, account.signout())
            elif self.path == '/api/account/usage':
                webbrowser.open('https://chatgpt.com/settings/usage')
            elif self.path == '/api/chat':
                microphone.stop()
                voice.stop()
                return self.send(200, conversation.start(payload.get('text')))
            elif self.path == '/api/chat/cancel':
                conversation.cancel()
                voice.stop()
            elif self.path == '/api/chat/clear':
                conversation.clear()
                voice.stop()
            elif self.path == '/api/microphone/start':
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
                if native_window:
                    native_window.destroy()
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            elif self.path == '/api/memories':
                text = payload.get('text', '')
                if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
                    return self.send(400, {'error': '기억은 1~2000자로 입력하세요.'})
                with connect() as conn:
                    conn.execute('INSERT INTO memories(text) VALUES (?)', (text.strip(),))
            elif self.path == '/api/delete':
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
            if smoke:
                subprocess.run([str(ROOT / 'JarvisSpeech'), '--check'], check=True, stdout=subprocess.DEVNULL, timeout=10)
                def check_window():
                    try:
                        smoke_result['ok'] = bool(native_window.evaluate_js("document.querySelector('input[type=password]') !== null"))
                    finally:
                        native_window.destroy()
                native_window.events.loaded += check_window
                watchdog = threading.Timer(40, native_window.destroy)
                watchdog.daemon = True
                watchdog.start()
            webview.start(gui='cocoa', debug=False, private_mode=True)
            if smoke:
                watchdog.cancel()
                if not smoke_result['ok']:
                    raise RuntimeError('Native WebKit window did not load the setup page')
            server.shutdown()
            thread.join(timeout=5)
    except KeyboardInterrupt:
        pass
    finally:
        microphone.stop()
        conversation.cancel()
        phone.stop()
        scanner.cancel()
        voice.stop()
        server.server_close()
