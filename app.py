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
from security import Scanner
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
speech_lock = threading.Lock()
speech = None
scanner = Scanner(DATA / 'scans')

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

    def send(self, status, value, content_type='application/json; charset=utf-8'):
        body = value.encode() if isinstance(value, str) else json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.headers.get('Host') != f'127.0.0.1:{PORT}':
            return self.send(403, {'error': '잘못된 접근 주소입니다.'})
        if self.path == '/':
            return self.send(200, (ROOT / 'index.html').read_text().replace('__TOKEN__', TOKEN), 'text/html; charset=utf-8')
        if self.path in ('/cyber.js', '/cyber.css'):
            kind = 'application/javascript' if self.path.endswith('.js') else 'text/css'
            return self.send(200, (ROOT / self.path[1:]).read_text(), kind + '; charset=utf-8')
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
            if self.path == '/api/scan':
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
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    if '--no-browser' not in sys.argv:
        webbrowser.open(ORIGIN)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        scanner.cancel()
        server.server_close()
        if speech and speech.poll() is None:
            speech.terminate()
