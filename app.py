"""JARVIS local prototype. Python 3.9+, no extra dependencies."""
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import threading
import webbrowser
from auth import Auth, AuthError, read_cookie, session_cookie_header, cleared_session_cookie_header
from security import Scanner
from phone import PhoneBridge, NumericHTTPServer
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('JARVIS_DATA_DIR', str(Path.home() / 'Library/Application Support/JarvisCyber' if sys.platform == 'darwin' else ROOT / 'data')))
DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
DB = DATA / 'jarvis.sqlite3'
legacy_db = ROOT / 'data' / 'jarvis.sqlite3'
if not DB.exists() and legacy_db.exists() and legacy_db != DB:
    with sqlite3.connect(legacy_db) as old, sqlite3.connect(DB) as new:
        old.backup(new)
TOKEN = secrets.token_urlsafe(32)  # per-process CSRF token, embedded in every HTML page
PORT = int(os.environ.get('JARVIS_PORT', '8765'))
ORIGIN = f'http://127.0.0.1:{PORT}'
speech_lock = threading.Lock()
speech = None
scanner = Scanner(DATA / 'scans')
phone = PhoneBridge()
auth = Auth(DB)  # login is separate from the CSRF token: TOKEN proves "same page load", the session cookie proves "logged in"

def connect():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

with connect() as conn:
    conn.execute('CREATE TABLE IF NOT EXISTS memories (id INTEGER PRIMARY KEY, text TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
os.chmod(DB, 0o600)

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
        """Serve an HTML file from ROOT with __TOKEN__ filled in."""
        return self.send(200, (ROOT / name).read_text().replace('__TOKEN__', TOKEN), 'text/html; charset=utf-8')

    def do_GET(self):
        if self.headers.get('Host') != f'127.0.0.1:{PORT}':
            return self.send(403, {'error': '잘못된 접근 주소입니다.'})

        # --- auth gate for the page routes ---------------------------------
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

        if self.path in ('/cyber.js', '/cyber.css'):
            kind = 'application/javascript' if self.path.endswith('.js') else 'text/css'
            return self.send(200, (ROOT / self.path[1:]).read_text(), kind + '; charset=utf-8')

        # --- everything past this point is a data API: require a session ----
        if self.path.startswith('/api/'):
            if not self.is_authed():
                return self.send(401, {'error': '로그인이 필요합니다.'})
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
        global speech
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

            # --- auth endpoints: no session required yet, that's the point ---
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
                auth.revoke_session(read_cookie(self.headers.get('Cookie'), 'jarvis_session'))
                return self.send(200, {'ok': True}, headers={'Set-Cookie': cleared_session_cookie_header()})

            # --- everything else needs an existing, logged-in session --------
            if not self.is_authed():
                return self.send(401, {'error': '로그인이 필요합니다.'})

            if self.path == '/api/phone/enable':
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
            elif self.path in ('/api/speak', '/api/stop'):
                if sys.platform != 'darwin':
                    return self.send(400, {'error': '기본 음성은 맥에서 실행할 때 사용할 수 있어요.'})
                text = payload.get('text', '')
                if not isinstance(text, str) or len(text) > 2000:
                    raise ValueError()
                with speech_lock:
                    if speech and speech.poll() is None:
                        speech.terminate()
                        speech.wait(timeout=3)
                    if self.path == '/api/speak' and text.strip():
                        speech = subprocess.Popen(['/usr/bin/say'], stdin=subprocess.PIPE)
                        speech.stdin.write(text.encode())
                        speech.stdin.close()
            else:
                return self.send(404, {'error': '찾을 수 없습니다.'})
            self.send(200, {'ok': True})
        except (ValueError, TypeError) as e:
            self.send(400, {'error': str(e) or '입력 형식을 확인하세요.'})
        except (OSError, sqlite3.Error, subprocess.SubprocessError):
            self.send(500, {'error': '처리하지 못했어요. 다시 시도해 주세요.'})

if __name__ == '__main__':
    if sys.stdout:
        print(f'JARVIS: {ORIGIN} (종료: Ctrl+C)', flush=True)
    server = NumericHTTPServer(('127.0.0.1', PORT), Handler)
    if '--no-browser' not in sys.argv:
        webbrowser.open(ORIGIN)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        phone.stop()
        scanner.cancel()
        server.server_close()
        if speech and speech.poll() is None:
            speech.terminate()
