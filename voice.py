"""Fish Audio adapter. Credentials live only in the macOS Keychain."""
import json
import re
import subprocess
import tempfile
import threading
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path


def extract_key(document):
    if not isinstance(document, str) or len(document) > 20000:
        raise ValueError('키 파일 형식을 확인하세요.')
    if document.lstrip().startswith('{\\rtf'):
        document = re.sub(r'\\[a-zA-Z]+-?\d* ?', '', document)
        document = re.sub(r'[{}\\\n\r]', ' ', document)
    candidates = re.findall(r'[A-Za-z0-9_.-]{24,}', document)
    if len(candidates) != 1:
        raise ValueError('API 키 하나가 들어 있는 TXT 또는 RTF 파일을 선택하세요.')
    return candidates[0]


class Voice:
    def __init__(self, directory):
        self.config = Path(directory) / 'voice.json'
        self.lock = threading.RLock()
        self.generation = 0
        self.player = None
        self.audio_path = None
        self.state = 'idle'
        self.error = ''

    def keychain(self):
        # Explicit backend: never fall back to a plaintext keyring.
        from keyring.backends.macOS import Keyring
        return Keyring()

    def settings(self):
        try:
            data = json.loads(self.config.read_text())
            if not data.get('reference_id'):
                data['reference_id'] = '612b878b113047d9a770c069c8b4fdfe'
            return data
        except (OSError, ValueError):
            return {'reference_id': '612b878b113047d9a770c069c8b4fdfe', 'model': 's2.1-pro-free'}

    def snapshot(self):
        with self.lock:
            if self.state == 'playing' and self.player and self.player.poll() is not None:
                self.state = 'idle'
                self.cleanup()
            try:
                configured = bool(self.keychain().get_password('space.jarvis.cyber.fish', 'api-key'))
            except Exception:
                configured = False
            return {**self.settings(), 'configured': configured, 'status': self.state, 'error': self.error}

    def save(self, payload):
        reference = payload.get('reference_id', '')
        model = payload.get('model', 's2.1-pro-free')
        if not isinstance(reference, str) or (reference and not re.fullmatch(r'[a-fA-F0-9]{32}', reference)):
            raise ValueError('Fish Audio 음성의 32자리 모델 ID를 입력하세요.')
        if model not in ('s1', 's2-pro', 's2.1-pro', 's2.1-pro-free'):
            raise ValueError('지원하는 TTS 엔진을 선택하세요.')
        if payload.get('key_document'):
            key = extract_key(payload['key_document'])
            try:
                self.keychain().set_password('space.jarvis.cyber.fish', 'api-key', key)
            except Exception:
                raise ValueError('macOS 키체인에 키를 저장하지 못했어요.') from None
        self.config.write_text(json.dumps({'reference_id': reference, 'model': model}))
        self.config.chmod(0o600)
        return self.snapshot()

    def request(self, path, body=None, model=None):
        try:
            key = self.keychain().get_password('space.jarvis.cyber.fish', 'api-key')
        except Exception:
            raise ValueError('macOS 키체인을 열지 못했어요.') from None
        if not key:
            raise ValueError('음성 설정에서 Fish Audio 키 파일을 가져오세요.')
        headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'}
        if model:
            headers['model'] = model
        req = urllib.request.Request('https://api.fish.audio/' + path,
            data=json.dumps(body).encode() if body is not None else None, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=40) as response:
                return response.read(16 * 1024 * 1024)
        except urllib.error.HTTPError as e:
            raise ValueError({401: 'Fish Audio API 키가 유효하지 않아요.', 402: 'Fish Audio 잔액 또는 요금제를 확인하세요.', 429: '음성 요청이 많아요. 잠시 후 다시 시도하세요.'}.get(e.code, 'Fish Audio 요청 실패 (HTTP %s)' % e.code)) from None
        except (OSError, urllib.error.URLError):
            raise ValueError('Fish Audio에 연결하지 못했어요. 인터넷 연결을 확인하세요.') from None

    def models(self, query):
        if not isinstance(query, str) or len(query) > 80:
            raise ValueError('검색어를 확인하세요.')
        data = json.loads(self.request('model?' + urllib.parse.urlencode({'title': query, 'page_size': 100})))
        return {'items': [{'id': x['_id'], 'title': x.get('title', ''), 'author': x.get('author', {}).get('nickname', '')} for x in data.get('items', [])]}

    def cleanup(self):
        if self.audio_path:
            self.audio_path.unlink(missing_ok=True)
            self.audio_path = None

    def stop(self):
        with self.lock:
            self.generation += 1
            if self.player and self.player.poll() is None:
                self.player.terminate()
                self.player.wait(timeout=3)
            self.player = None
            self.cleanup()
            self.state = 'idle'

    def speak(self, text):
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            raise ValueError('읽을 내용을 1~2000자로 입력하세요.')
        config = self.settings()
        if not config['reference_id']:
            raise ValueError('음성 설정에서 자비스 음성을 검색하거나 모델 ID를 지정하세요.')
        self.stop()
        with self.lock:
            generation = self.generation
            self.state, self.error = 'generating', ''
        def worker():
            try:
                audio = self.request('v1/tts', {'text': text, 'reference_id': config['reference_id'], 'format': 'mp3'}, config['model'])
                with self.lock:
                    if generation != self.generation:
                        return
                    with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f:
                        f.write(audio)
                        self.audio_path = Path(f.name)
                    self.player = subprocess.Popen(['/usr/bin/afplay', str(self.audio_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.state = 'playing'
            except Exception as e:
                with self.lock:
                    if generation == self.generation:
                        self.state = 'error'
                        self.error = str(e) if isinstance(e, ValueError) else '음성 재생에 실패했어요.'
                        self.cleanup()
        threading.Thread(target=worker, daemon=True).start()
        return {'ok': True}
