"""Supabase user-scoped storage. No administrative keys or on-disk data cache."""
import hashlib
import base64
import secrets
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from network import tls_context

URL = 'https://xflhofkqakxhagtbwycp.supabase.co'
KEY = 'sb_publishable_5-W7IV0W72mB7yw9Ae4iZg_Ajdoi3ny'
SERVICE = 'space.jarvis.cyber.supabase'

class Cloud:
    def __init__(self, vault=None):
        self._vault = vault
        self.lock = threading.RLock()
        self.session = None
        self.cache = {}
        self.pending_email = None
        self.last_otp = 0
        self.verifier = None
        self.pending_until = 0
        self.error = ''
        self.device = None
        self.bound_user = None
        try:
            raw = self.vault().get_password(SERVICE, 'session')
            self.session = json.loads(raw) if raw else None
            self.device = self.vault().get_password(SERVICE, 'device')
            self.bound_user = self.session['user']['id'] if self.session else None
        except Exception:
            pass

    def vault(self):
        if self._vault is None:
            from keyring.backends.macOS import Keyring
            self._vault = Keyring()
        return self._vault

    def request(self, path, body=None, method=None, authenticated=True, headers=None, binary=False):
        h = {'apikey': KEY, **(headers or {})}
        if authenticated:
            h['Authorization'] = 'Bearer ' + self.access()
        if body is not None and not isinstance(body, bytes):
            body = json.dumps(body).encode()
            h['Content-Type'] = 'application/json'
        req = urllib.request.Request(URL + path, data=body, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=25, context=tls_context()) as r:
                data = r.read(17 * 1024 * 1024)
                return data if binary else (json.loads(data) if data else None)
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read(8192))
                code = detail.get('error_code') or detail.get('code') or detail.get('error')
            except (ValueError, AttributeError):
                code = None
            messages = {
                'otp_expired':'이 링크는 이미 사용했거나 만료됐어요. 새 인증 메일을 요청하세요.',
                'over_email_send_rate_limit':'Supabase 인증 메일 발송 한도에 도달했어요. 잠시 기다린 뒤 다시 요청하세요. 같은 링크를 반복해 열지 마세요.',
                'over_request_rate_limit':'인증 요청이 너무 많아요. 잠시 기다린 뒤 다시 시도하세요.',
                'bad_code_verifier':'인증을 요청한 앱과 다른 세션이에요. 앱에서 새 메일을 요청하세요.',
                'flow_state_not_found':'인증 대기가 만료됐어요. 앱에서 새 메일을 요청하세요.'}
            if code in messages:
                raise ValueError(messages[code]) from None
            raise ValueError({400:'인증번호 또는 요청을 확인하세요.',401:'클라우드에 다시 로그인하세요.',403:'클라우드 접근 권한이 없어요. 프로젝트 소유자 이메일을 사용하세요.',404:'클라우드 저장 항목을 찾지 못했어요.',422:'이메일 또는 인증번호를 확인하세요.',429:'인증 요청이 많아요. 잠시 후 다시 시도하세요.'}.get(e.code, f'클라우드 요청 실패 (HTTP {e.code}). 저장되지 않았어요.')) from None
        except (OSError, urllib.error.URLError):
            raise ValueError('Supabase에 연결하지 못했어요. 인터넷 연결을 확인하세요. 저장은 완료되지 않았어요.') from None

    def access(self):
        with self.lock:
            if not self.session:
                raise ValueError('먼저 클라우드 저장소에 로그인하세요.')
            if self.session['expires_at'] < time.time() + 60:
                data = self.request('/auth/v1/token?grant_type=refresh_token', {'refresh_token':self.session['refresh_token']}, authenticated=False)
                self.accept(data)
            return self.session['access_token']

    def accept(self, data):
        # Validate server-side identity before persisting or granting a local session.
        token = data['access_token']
        user = self.request('/auth/v1/user', authenticated=False, headers={'Authorization':'Bearer '+token})
        if self.bound_user and user['id'] != self.bound_user:
            raise ValueError('다른 저장소 계정으로 바꾸려면 앱을 종료하고 다시 실행하세요.')
        if self.pending_email and user.get('email','').lower() != self.pending_email.lower():
            raise ValueError('인증 메일을 요청한 계정과 다른 로그인 링크예요.')
        session = {'access_token':token,'refresh_token':data['refresh_token'],
                   'expires_at':time.time()+data.get('expires_in',3600),'user':{'id':user['id'],'email':user.get('email','')}}
        try:
            self.vault().set_password(SERVICE,'session',json.dumps(session))
            if not self.device:
                self.device = str(uuid.uuid4())
                self.vault().set_password(SERVICE,'device',self.device)
        except Exception:
            raise ValueError('macOS 키체인 접근을 허용하세요. 세션을 안전하게 저장하지 못했어요.') from None
        self.session = session
        self.bound_user = user['id']
        self.cache.clear()

    def otp(self, email):
        if not isinstance(email,str) or len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
            raise ValueError('이메일 주소를 확인하세요.')
        with self.lock:
            if time.time()-self.last_otp < 60:
                raise ValueError('인증 메일은 60초 후 다시 요청할 수 있어요.')
            verifier = secrets.token_urlsafe(48)
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
            self.request('/auth/v1/otp?redirect_to=http%3A%2F%2Flocalhost%3A3000',{'email':email,'create_user':True,'code_challenge':challenge,'code_challenge_method':'s256'},authenticated=False)
            self.verifier = verifier
            self.pending_until = time.time()+3600
            self.error = ''
            self.pending_email = email
            self.last_otp = time.time()
        return {'ok':True}

    def complete(self, code):
        with self.lock:
            if not self.pending_email or not self.verifier or time.time()>self.pending_until:
                raise ValueError('인증을 요청한 앱을 켜 둔 상태에서 최신 메일을 여세요. 앱을 재시작했다면 새 메일이 필요해요.')
            if not isinstance(code,str) or not 1 <= len(code) <= 2048:
                raise ValueError('로그인 복귀 코드가 올바르지 않아요.')
            try:
                data = self.request('/auth/v1/token?grant_type=pkce', {'auth_code':code,'code_verifier':self.verifier},authenticated=False)
                self.accept(data)
            except ValueError as e:
                self.error = str(e)
                raise
            self.pending_email = None
            self.verifier = None
            self.error = ''
        return self.status()

    def verify(self, token):
        with self.lock:
            if not self.pending_email or not isinstance(token,str) or len(token)>4096:
                raise ValueError('인증 메일을 먼저 요청하세요.')
            if re.fullmatch(r'\d{6,10}',token):
                body = {'email':self.pending_email,'token':token,'type':'email'}
            else:
                parsed = urllib.parse.urlsplit(token)
                query = urllib.parse.parse_qs(parsed.query)
                if parsed.scheme=='http' and parsed.netloc in ('localhost:3000','127.0.0.1:3000') and parsed.path in ('','/') and len(query.get('code',[]))==1:
                    return self.complete(query['code'][0])
                if (parsed.scheme!='https' or parsed.netloc!=urllib.parse.urlsplit(URL).netloc
                        or parsed.path!='/auth/v1/verify' or len(query.get('token',[]))!=1
                        or query.get('type') not in (['magiclink'],['signup'],['email'])):
                    raise ValueError('메일의 로그인 버튼에서 링크 주소를 복사해 붙여넣으세요.')
                body = {'token_hash':query['token'][0],'type':'email'}
            data = self.request('/auth/v1/verify',body,authenticated=False)
            self.accept(data)
            self.pending_email = None
            self.verifier = None
        return self.status()

    def status(self):
        return {'connected':bool(self.session),'email':self.session['user']['email'] if self.session else '', 'project':'xflhofkqakxhagtbwycp','pending':bool(self.pending_email),'retry_after':max(0,int(60-(time.time()-self.last_otp))),'error':self.error}

    def resume(self):
        self.access()
        self.request('/auth/v1/user')
        return self.status()

    def signout(self):
        with self.lock:
            if self.session:
                self.request('/auth/v1/logout?scope=local',{},method='POST')
            try:
                self.vault().delete_password(SERVICE,'session')
            except Exception:
                raise ValueError('키체인의 세션을 지우지 못했어요.') from None
            self.session = None
            self.pending_email = None
            self.verifier = None
            self.cache.clear()

    def uid(self):
        self.access()
        return self.session['user']['id']

    def records(self, kind, account=None, limit=100):
        query = {'user_id':'eq.'+self.uid(),'kind':'eq.'+kind,'order':'created_at.desc,id.desc','limit':str(limit)}
        if account is not None:
            query['payload->>account'] = 'eq.'+account
        key = json.dumps(query,sort_keys=True)
        with self.lock:
            hit = self.cache.get(key)
            if hit and time.time()-hit[0]<3:
                return hit[1]
            rows = self.request('/rest/v1/jarvis_records?'+urllib.parse.urlencode(query))
            self.cache[key] = (time.time(),rows)
            return rows

    def put(self, kind, payload, record_id=None):
        uid = self.uid()
        row = {'user_id':uid,'id':record_id or str(uuid.uuid4()),'kind':kind,'payload':payload,
               'updated_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
        self.request('/rest/v1/jarvis_records?on_conflict=user_id,id',row,headers={'Prefer':'resolution=merge-duplicates'})
        with self.lock:
            self.cache.clear()
        return row

    def delete(self, kind, record_id=None, account=None):
        query = {'user_id':'eq.'+self.uid(),'kind':'eq.'+kind}
        if record_id is not None:
            query['id'] = 'eq.'+str(uuid.UUID(str(record_id)))
        elif account is None:
            raise ValueError('삭제할 항목을 지정하세요.')
        if account is not None:
            query['payload->>account'] = 'eq.'+account
        self.request('/rest/v1/jarvis_records?'+urllib.parse.urlencode(query),method='DELETE')
        with self.lock:
            self.cache.clear()

    def settings_id(self,name):
        return str(uuid.uuid5(uuid.NAMESPACE_URL,'jarvis:'+name))

    def setting(self,name,default=None):
        query = urllib.parse.urlencode({'user_id':'eq.'+self.uid(),'id':'eq.'+self.settings_id(name)})
        key = 'setting:'+name
        with self.lock:
            if key in self.cache:
                return self.cache[key]
            rows = self.request('/rest/v1/jarvis_records?'+query)
            value = rows[0]['payload'] if rows else default
            self.cache[key] = value
            return value

    def save_setting(self,name,value):
        self.put('settings',value,self.settings_id(name))

    def messages(self,account,limit=100):
        return [{'id':r['id'],**r['payload']} for r in reversed(self.records('message',account,limit))]

    def memories(self):
        return [{'id':r['id'],**r['payload']} for r in self.records('memory',limit=1000)]

    def blob(self,name,data=None,content_type='application/octet-stream'):
        path = '/storage/v1/object/jarvis-private/'+self.uid()+'/'+urllib.parse.quote(name,safe='/')
        if data is None:
            return self.request(path,binary=True)
        self.request(path,data,method='POST',headers={'Content-Type':content_type,'x-upsert':'true'})

    def audio(self,text,reference,model,generate):
        name = 'tts/'+hashlib.sha256(json.dumps([text,reference,model]).encode()).hexdigest()+'.mp3'
        try:
            return self.blob(name)
        except ValueError as e:
            if '찾지 못했어요' not in str(e):
                # Storage can report missing objects as 400; do not hide network errors.
                if '인증번호 또는 요청' not in str(e):
                    raise
        data = generate()
        self.blob(name,data,'audio/mpeg')
        return data

class RuntimeAuth:
    """Loopback UI sessions last only for this application process."""
    def __init__(self):
        self.sessions = {}
    def has_password(self):
        return True
    def issue_session(self):
        import secrets
        token = secrets.token_urlsafe(32)
        self.sessions[token] = time.time()+86400
        return token
    def verify_session(self,token):
        return self.sessions.get(token,0)>time.time()
    def revoke_session(self,token):
        self.sessions.pop(token,None)
