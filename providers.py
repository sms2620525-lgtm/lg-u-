"""OpenRouter preferences in Supabase; API credentials only in macOS Keychain."""
import json
import re
import threading
import urllib.error
import urllib.request
from network import tls_context

BASE = 'https://openrouter.ai/api/v1'
SERVICE = 'space.jarvis.cyber.openrouter'
TONES = {
    'jarvis': '차분하고 유능한 자비스 같은 비서로 말하세요. 간결한 한국어 존댓말(합니다/하겠습니다)을 사용하고 핵심부터 답하세요. 과장, 아부, 반복적인 인사, 불필요한 감탄사는 피하세요.',
    'friendly': '친한 동료처럼 자연스럽고 편한 한국어 반말로 답하세요. 무례함과 과한 유행어는 피하고 핵심부터 간결하게 설명하세요.',
    'formal': '정중한 한국어 존댓말로 정확하고 명료하게 답하세요. 요청에 필요한 설명을 충분히 제공하세요.'
}


def api_error(code):
    return {401:'OpenRouter API 키가 유효하지 않습니다. 키를 다시 저장해 주세요.',
            402:'OpenRouter 크레딧이 부족합니다. 잔액을 확인해 주세요.',
            403:'OpenRouter 모델 접근 권한 또는 데이터 정책을 확인해 주세요.',
            429:'OpenRouter 요청 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.',
            400:'OpenRouter 모델 또는 요청을 확인해 주세요.'}.get(code, 'OpenRouter 응답에 실패했습니다. 연결과 모델 상태를 확인해 주세요.')


def request(path, key=None):
    headers = {'Authorization':'Bearer '+key} if key else {}
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE+path, headers=headers), context=tls_context(), timeout=30) as response:
            return json.loads(response.read(8*1024*1024))
    except urllib.error.HTTPError as exc:
        raise ValueError(api_error(exc.code)) from None
    except (OSError, ValueError):
        raise ValueError('OpenRouter에 연결하지 못했습니다. 인터넷 연결을 확인해 주세요.') from None


class Providers:
    def __init__(self, account, cloud=None, vault=None):
        self.account, self.cloud, self._vault = account, cloud, vault
        self.local = {'provider':'chatgpt', 'model':'', 'tone':'jarvis'}
        self.catalog = []
        self.lock = threading.RLock()

    def settings(self):
        return self.cloud.setting('assistant', self.local) if self.cloud else dict(self.local)

    def save(self, payload):
        with self.lock:
            data = dict(self.settings())
            for name, allowed in [('provider', ('chatgpt','openrouter')), ('tone', TONES)]:
                if name in payload:
                    if payload[name] not in allowed:
                        raise ValueError('지원하지 않는 설정입니다.')
                    data[name] = payload[name]
            if 'model' in payload:
                if payload['model'] not in [m['id'] for m in self.catalog]:
                    raise ValueError('목록에서 OpenRouter 모델을 선택해 주세요.')
                data['model'] = payload['model']
            if self.cloud:
                self.cloud.save_setting('assistant', data)
            else:
                self.local = data
            return self.public()

    def vault(self):
        if self._vault is None:
            from keyring.backends.macOS import Keyring
            self._vault = Keyring()
        return self._vault

    def key_id(self):
        return self.cloud.uid() if self.cloud else 'local-test'

    def key(self):
        try:
            return self.vault().get_password(SERVICE, self.key_id()) or ''
        except Exception:
            raise ValueError('OpenRouter 키의 macOS 키체인 접근을 허용해 주세요.') from None

    def save_key(self, key):
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{20,512}', key.strip()):
            raise ValueError('올바른 OpenRouter API 키를 입력해 주세요.')
        key = key.strip()
        request('/key', key)  # Validate without generating a paid response.
        try:
            self.vault().set_password(SERVICE, self.key_id(), key)
        except Exception:
            raise ValueError('OpenRouter 키를 키체인에 저장하지 못했습니다.') from None
        return self.public()

    def delete_key(self):
        try:
            if self.key():
                self.vault().delete_password(SERVICE, self.key_id())
        except Exception:
            raise ValueError('키체인에서 OpenRouter 키를 삭제하지 못했습니다.') from None
        return self.public()

    def public(self):
        data = self.settings()
        try:
            configured = bool(self.key())
        except ValueError:
            configured = False
        return {**data, 'configured':configured}

    def ready(self):
        data = self.public()
        if data['provider'] == 'openrouter':
            return {'connected': data['configured'] and bool(data.get('model')), 'plan_enabled':True}
        return self.account.public()

    def models(self):
        data = request('/models')
        self.catalog = sorted([
            {'id':m['id'], 'name':m.get('name',m['id']), 'pricing':m.get('pricing',{})}
            for m in data.get('data', [])
            if 'text' in m.get('architecture',{}).get('output_modalities',['text'])
            and 'text' in m.get('architecture',{}).get('input_modalities',['text'])
        ], key=lambda m:m['name'].lower())
        if not self.catalog:
            raise ValueError('OpenRouter 대화 모델 목록을 불러오지 못했습니다.')
        return {'models':self.catalog, 'model':self.settings().get('model','')}

    def instructions(self):
        return TONES.get(self.settings().get('tone'), TONES['jarvis'])

    def greeting(self):
        return '응, 듣고 있어.' if self.settings().get('tone') == 'friendly' else '네, 말씀하십시오.'
