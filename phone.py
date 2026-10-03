"""Opt-in LAN motion receiver. Never exposes memory or scan endpoints."""
import hmac
import json
import math
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class PhoneBridge:
    def __init__(self):
        self.lock = threading.Lock()
        self.server = None
        self.pin = ''
        self.token = ''
        self.expires = 0
        self.attempts = 0
        self.motion = {'pitch': 0, 'roll': 0, 'updated': 0}

    def snapshot(self):
        with self.lock:
            return {'enabled': self.server is not None,
                    'connected': bool(self.token) and time.time()-self.motion['updated'] < 2,
                    'pitch': self.motion['pitch'], 'roll': self.motion['roll']}

    def accept(self, path, payload, bearer=''):
        with self.lock:
            if path == '/pair':
                if self.attempts >= 5 or time.time() > self.expires or not self.pin:
                    return 403, {'error': '맥에서 새 연결 코드를 발급하세요.'}
                self.attempts += 1
                pin = payload.get('pin')
                if not isinstance(pin, str) or not hmac.compare_digest(pin, self.pin):
                    return 403, {'error': '연결 코드가 다릅니다.'}
                self.token = secrets.token_urlsafe(32)
                self.pin = ''
                self.session_expiry = time.time() + 3600
                return 200, {'token': self.token}
            if path == '/motion':
                if not self.token or not hmac.compare_digest(bearer, 'Bearer '+self.token) or time.time() > self.session_expiry:
                    return 403, {'error': '다시 연결하세요.'}
                values = [payload.get('pitch'), payload.get('roll')]
                if any(type(v) not in (int, float) or not math.isfinite(v) or abs(v)>180 for v in values):
                    return 400, {'error': '잘못된 회전 값'}
                self.motion = {'pitch': values[0], 'roll': values[1], 'updated': time.time()}
                return 200, {'ok': True}
            return 404, {'error': '찾을 수 없습니다.'}

    def enable(self):
        if self.server is None:
            owner = self
            class Receiver(BaseHTTPRequestHandler):
                def log_message(self, *args): pass
                def do_POST(self):
                    try:
                        size=int(self.headers.get('Content-Length','0'))
                        if not 0<size<=1024: raise ValueError()
                        data=json.loads(self.rfile.read(size))
                        if not isinstance(data,dict): raise ValueError()
                        code,result=owner.accept(self.path,data,self.headers.get('Authorization',''))
                    except (ValueError,TypeError):
                        code,result=400,{'error':'Invalid input'}
                    body=json.dumps(result).encode()
                    self.send_response(code);self.send_header('Content-Type','application/json')
                    self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
                def setup(self):
                    super().setup();self.connection.settimeout(5)
            self.server=ThreadingHTTPServer(('0.0.0.0',8766),Receiver)
            threading.Thread(target=self.server.serve_forever,daemon=True).start()
        with self.lock:
            self.pin=f'{secrets.randbelow(1000000):06d}'
            self.token='';self.attempts=0;self.expires=time.time()+300
            pin=self.pin
        ips=[]
        if sys.platform=='darwin':
            for interface in ('en0','en1','en2'):
                try:
                    result=subprocess.run(['/usr/sbin/ipconfig','getifaddr',interface],capture_output=True,text=True,timeout=2)
                    if result.returncode==0 and result.stdout.strip(): ips.append(result.stdout.strip())
                except (OSError,subprocess.SubprocessError): pass
        return {'pin':pin,'addresses':list(dict.fromkeys(ips)),'port':8766,'expires_in':300}

    def stop(self):
        if self.server:
            self.server.shutdown();self.server.server_close();self.server=None
        with self.lock:
            self.pin='';self.token='';self.motion['updated']=0
