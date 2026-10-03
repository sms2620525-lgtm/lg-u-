import json
import tempfile
import time
import unittest
import urllib.parse
from unittest.mock import Mock, patch
from chatgpt import ChatGPT, SERVICE, AUTH

class Vault:
    def __init__(self): self.values = {}
    def get_password(self, service, key): return self.values.get((service, key))
    def set_password(self, service, key, value): self.values[service, key] = value

class AccountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vault = Vault()
        self.client = ChatGPT(self.tmp.name, 'http://127.0.0.1:8765/auth/callback', self.vault)

    def begin(self):
        with patch('chatgpt.webbrowser.open', return_value=True) as browser:
            self.client.begin()
            return urllib.parse.parse_qs(urllib.parse.urlparse(browser.call_args[0][0]).query)

    def test_host_persists_and_pkce_changes(self):
        first = self.begin()
        second = self.begin()
        self.assertEqual(first['ext_agent_host_id'], second['ext_agent_host_id'])
        self.assertNotEqual(first['state'], second['state'])
        self.assertNotEqual(first['code_challenge'], second['code_challenge'])
        self.assertEqual(second['code_challenge_method'], ['S256'])
        self.assertEqual(ChatGPT(self.tmp.name, self.client.redirect_uri, self.vault).meta['host'], self.client.meta['host'])

    def test_bad_state_and_denied_consent_never_exchange(self):
        self.begin()
        with patch('chatgpt.http_json') as request:
            with self.assertRaises(ValueError): self.client.complete({'state': 'attacker', 'code': 'code'})
            request.assert_not_called()
            state = self.client.pending['state']
            with self.assertRaises(ValueError): self.client.complete({'state': state, 'error': 'access_denied'})
            request.assert_not_called()
            self.assertIsNone(self.client.pending)

    def test_new_login_uses_issued_id_and_keeps_secrets_out_of_ui_and_disk(self):
        self.begin()
        state = self.client.pending['state']
        tokens = {'id_token':'SECRET_ID','access_token':'SECRET_ACCESS','refresh_token':'SECRET_REFRESH','scope':'openid chatgpt.tokens.use.direct','expires_in':3600}
        with patch('chatgpt.http_json', return_value=tokens) as request, patch.object(self.client,'validate_id',return_value={'sub':'user-one','email':'test@example.com'}):
            result = self.client.complete({'state':state,'code':'code','client_id':'oaiapp_issued'})
            self.assertEqual(request.call_args[0][1]['client_id'], 'oaiapp_issued')
        self.assertTrue(result['plan_enabled'])
        self.assertNotIn('SECRET_', str(result))
        self.assertNotIn('SECRET_', self.client.path.read_text())
        self.assertIn('SECRET_ACCESS', self.vault.get_password(SERVICE,'oaiapp_issued'))
        with self.assertRaises(ValueError): self.client.complete({'state':state,'code':'code','client_id':'oaiapp_issued'})

    def test_identity_only_does_not_allow_inference(self):
        self.begin()
        with patch('chatgpt.http_json', return_value={'id_token':'id','scope':'openid','access_token':'access'}), patch.object(self.client,'validate_id',return_value={'sub':'user-one'}):
            result = self.client.complete({'state':self.client.pending['state'],'code':'code','client_id':'oaiapp_identity'})
        self.assertFalse(result['plan_enabled'])
        with self.assertRaises(ValueError): self.client.access()

    def test_refresh_rotates_tokens_together(self):
        self.client.meta['active']='oaiapp_one'
        self.client.meta['accounts']['oaiapp_one']={'subject':'one','connected':True,'plan_enabled':True}
        self.client.save_credentials('oaiapp_one',{'refresh_token':'old','expires_at':0,'scope':'chatgpt.tokens.use.direct'})
        with patch('chatgpt.http_json',return_value={'access_token':'new_access','refresh_token':'new_refresh','expires_in':3600}) as request:
            self.assertEqual(self.client.access(),'new_access')
            self.assertEqual(request.call_args[0][1]['refresh_token'],'old')
        self.assertEqual(self.client.credentials('oaiapp_one')['refresh_token'],'new_refresh')

    def test_jwt_signature_nonce_and_audience(self):
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        claims={'iss':AUTH,'aud':'oaiapp_one','sub':'one','exp':time.time()+60,'nonce':'correct'}
        token=jwt.encode(claims,key,algorithm='RS256')
        with patch.object(self.client,'discover',return_value={'jwks_uri':AUTH+'/.well-known/jwks.json'}), patch('jwt.PyJWKClient') as jwks:
            jwks.return_value.get_signing_key_from_jwt.return_value=Mock(key=key.public_key())
            self.assertEqual(self.client.validate_id(token,'oaiapp_one','correct')['sub'],'one')
            with self.assertRaises(ValueError): self.client.validate_id(token,'oaiapp_one','wrong')
            with self.assertRaises(ValueError): self.client.validate_id(token,'oaiapp_two','correct')
            with self.assertRaises(ValueError): self.client.validate_id(token[:-8]+'tampered','oaiapp_one','correct')

class ConversationTests(unittest.TestCase):
    def test_stream_commits_only_completed_answers(self):
        import sqlite3
        import threading
        from pathlib import Path
        from chatgpt import Conversation
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'test.sqlite'
            def connect():
                c=sqlite3.connect(path); c.row_factory=sqlite3.Row;return c
            with connect() as c:c.execute('CREATE TABLE memories(id INTEGER PRIMARY KEY, text TEXT)')
            account=Mock()
            account.meta={'active':'account-a','accounts':{'account-a':{'model':'test-model'}}}
            account.catalog=[{'id':'test-model'}]
            account.access.return_value='FAKE_TOKEN'
            chat=Conversation(account,connect)
            class Stream:
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def __iter__(self):
                    yield b'data: {"type":"response.output_text.delta","delta":"hello"}\n'
                    yield b'data: {"type":"response.completed"}\n'
            with patch('chatgpt.urllib.request.urlopen',return_value=Stream()) as request:
                chat.start('hi')
                for t in threading.enumerate():
                    if t.name.endswith('(worker)'):t.join(2)
                sent=json.loads(request.call_args[0][0].data)
                self.assertFalse(sent['store'])
                self.assertTrue(sent['stream'])
                self.assertNotIn('previous_response_id',sent)
                self.assertEqual(chat.snapshot()['messages'][-1]['text'],'hello')
            class Broken(Stream):
                def __iter__(self):yield b'data: {"type":"response.output_text.delta","delta":"unfinished"}\n'
            with patch('chatgpt.urllib.request.urlopen',return_value=Broken()):
                chat.start('second')
                for t in threading.enumerate():
                    if t.name.endswith('(worker)'):t.join(2)
                self.assertEqual(chat.snapshot()['status'],'error')
                self.assertEqual([x['text'] for x in chat.snapshot()['messages'] if x['role']=='assistant'],['hello'])
            account.meta['active']='account-b'
            self.assertEqual(chat.snapshot()['messages'],[])
