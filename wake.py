"""Window-independent, opt-in double-clap conversation controller."""
import threading
import time


class WakeController:
    def __init__(self, microphone, voice, conversation, account):
        self.mic, self.voice, self.chat, self.account = microphone, voice, conversation, account
        self.lock = threading.RLock()
        self.enabled = False
        self.phase = 'off'
        self.error = ''
        self.seq = 0
        self.queue = []
        self.deadline = 0
        threading.Thread(target=self._run, daemon=True).start()

    def snapshot(self):
        with self.lock:
            return dict(enabled=self.enabled, phase=self.phase, error=self.error)

    def _listen(self, mode):
        self.seq = self.mic.start(mode)['seq']
        self.phase = 'waiting' if mode == 'clap' else 'listening'
        self.deadline = time.monotonic() + 20

    def enable(self):
        with self.lock:
            status = self.account.public()
            if not status.get('connected') or not status.get('plan_enabled'):
                raise ValueError('먼저 ChatGPT 계정을 연결해 주세요.')
            if not self.voice.snapshot().get('configured'):
                raise ValueError('먼저 Fish Audio API 키를 설정해 주세요.')
            if not self.enabled:
                self.mic.stop()
                self.chat.cancel()
                self.voice.stop()
                self._listen('clap')
                self.enabled, self.error = True, ''
            return self.snapshot()

    def pause(self, disable=False):
        with self.lock:
            if self.enabled:
                self.mic.stop()
                if self.phase in ('thinking', 'speaking', 'greeting'):
                    self.chat.cancel()
                    self.voice.stop()
            self.queue = []
            self.phase = 'off' if disable else 'manual'
            if disable:
                self.enabled = False
            return self.snapshot()

    def resume(self):
        with self.lock:
            if self.enabled and self.phase == 'manual':
                self._listen('clap')
            return self.snapshot()

    def _tick(self):
        with self.lock:
            if not self.enabled or self.phase == 'manual':
                return
            if self.phase in ('waiting', 'listening'):
                data = self.mic.snapshot()
                if data['status'] == 'error':
                    raise ValueError(data['error'])
                for event in data['events']:
                    if event['seq'] <= self.seq:
                        continue
                    self.seq = event['seq']
                    if self.phase == 'waiting' and event['type'] == 'clap_pair':
                        self.mic.stop()
                        self.voice.speak('네, 듣고 있어요.')
                        self.phase = 'greeting'
                        return
                    if self.phase == 'listening' and event['type'] == 'utterance' and event.get('text', '').strip():
                        self.mic.stop()
                        self.chat.start(event['text'])
                        with self.chat.lock:
                            self.chat.state['background'] = True
                        self.phase = 'thinking'
                        return
                if self.phase == 'listening' and time.monotonic() > self.deadline:
                    self.mic.stop()
                    self._listen('clap')
            elif self.phase == 'thinking':
                with self.chat.lock:
                    status = dict(self.chat.state)
                if status['status'] == 'error':
                    raise ValueError(status['error'])
                if status['status'] == 'done':
                    messages = self.chat.snapshot()['messages']
                    text = next((m['text'] for m in reversed(messages) if m['role'] == 'assistant'), '')
                    self.queue = [text[i:i+1800] for i in range(0, len(text), 1800)]
                    self.phase = 'speaking'
                elif status['status'] == 'idle':
                    self._listen('clap')
            elif self.phase in ('greeting', 'speaking'):
                status = self.voice.snapshot()
                if status['status'] == 'error':
                    raise ValueError(status['error'])
                if status['status'] == 'idle':
                    if self.queue:
                        self.voice.speak(self.queue.pop(0))
                    else:
                        self._listen('speech')

    def _run(self):
        while True:
            try:
                self._tick()
            except Exception as exc:
                with self.lock:
                    self.pause(disable=True)
                    self.error = str(exc)
            time.sleep(.1)
