"""Native Apple Speech helper lifecycle and bounded event queue."""
import json
import subprocess
import threading
from collections import deque
from pathlib import Path

class Microphone:
    def __init__(self, root):
        self.executable = Path(root) / 'JarvisSpeech'
        self.process = None
        self.lock = threading.RLock()
        self.events = deque(maxlen=80)
        self.seq = 0
        self.status = 'off'
        self.error = ''
        self.mode = 'speech'

    def start(self, mode="speech"):
        if mode not in ("speech", "clap"):
            raise ValueError("지원하지 않는 마이크 모드예요.")
        if self.process and self.mode != mode:
            self.stop()
        with self.lock:
            if self.process and self.process.poll() is None:
                return self.snapshot()
            if not self.executable.exists():
                raise ValueError('음성 입력은 macOS DMG 앱에서 사용할 수 있어요.')
            self.mode = mode
            process = subprocess.Popen([str(self.executable)] + (['--clap'] if mode == 'clap' else []), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            self.process = process
            self.status, self.error = 'starting', ''
        def read():
            for line in process.stdout:
                try:
                    data = json.loads(line)
                except ValueError:
                    continue
                with self.lock:
                    if self.process is not process:
                        break
                    self.seq += 1
                    self.events.append({**data, 'seq': self.seq})
                    if data.get('type') == 'ready':
                        self.status = 'listening'
                    elif data.get('type') == 'error':
                        self.status, self.error = 'error', data.get('text', '음성 입력 오류')
            with self.lock:
                if self.process is process:
                    self.status = 'error'
                    self.error = self.error or '마이크 연결이 종료되었어요. 다시 켜 주세요.'
        threading.Thread(target=read, daemon=True).start()
        return self.snapshot()

    def stop(self):
        with self.lock:
            process, self.process = self.process, None
            self.status = 'off'
            self.events.clear()
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)

    def snapshot(self):
        with self.lock:
            return {'status': self.status, 'error': self.error, 'seq': self.seq, 'events': list(self.events), 'mode':self.mode}
