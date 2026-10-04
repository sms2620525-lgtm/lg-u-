import io
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch
from providers import Providers, SERVICE, request, BASE
from chatgpt import Conversation

class Vault:
    def __init__(self): self.values = {}
    def get_password(self, s, k): return self.values.get((s,k))
    def set_password(self, s, k, v): self.values[s,k] = v
    def delete_password(self, s, k): del self.values[s,k]

class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.vault = Vault()
        self.account = Mock(meta={'active':'gpt','accounts':{}})
        self.p = Providers(self.account, vault=self.vault)

    def test_validate_before_save_and_no_key_in_public_settings(self):
        key='test-secret-api-key-123456789'
        with patch('providers.request',return_value={'data':{}}) as req:
            self.p.save_key(key)
            req.assert_called_once_with('/key',key)
        self.assertTrue(self.p.public()['configured'])
        self.assertNotIn(key,json.dumps(self.p.public()))
        self.assertNotIn(key,json.dumps(self.p.local))
        with patch('providers.request',side_effect=ValueError('invalid')):
            with self.assertRaises(ValueError): self.p.save_key('another-api-key-123456789')
        self.assertEqual(self.p.key(),key)
        self.p.delete_key()
        self.assertFalse(self.p.public()['configured'])

    def test_cloud_settings_never_contain_secret_and_scope_key_to_user(self):
        cloud=Mock()
        cloud.uid.return_value='user-one'
        cloud.setting.return_value={'provider':'chatgpt','tone':'jarvis','model':''}
        p=Providers(self.account,cloud,self.vault)
        with patch('providers.request',return_value={'data':{}}):p.save_key('test-secret-api-key-123456789')
        p.save({'tone':'friendly'})
        args=cloud.save_setting.call_args.args
        self.assertEqual(args[0],'assistant')
        self.assertEqual(args[1]['tone'],'friendly')
        self.assertNotIn('secret',json.dumps(args))
        self.assertEqual(cloud.setting.return_value['tone'],'jarvis')
        cloud.uid.return_value='user-two'
        self.assertEqual(p.key(),'')

    def test_model_filter_selection_and_independent_readiness(self):
        with patch('providers.request',return_value={'data':[{'id':'a/text','name':'Text','architecture':{'output_modalities':['text']}},{'id':'b/image','architecture':{'output_modalities':['image']}}]}):
            self.assertEqual(len(self.p.models()['models']),1)
        with self.assertRaises(ValueError):self.p.save({'model':'not-in-catalog'})
        self.vault.set_password(SERVICE,'local-test','token')
        self.p.save({'provider':'openrouter','model':'a/text','tone':'friendly'})
        self.assertTrue(self.p.ready()['connected'])
        self.account.public.assert_not_called()
        self.assertIn('반말',self.p.instructions())
        self.assertEqual(self.p.greeting(),'응, 듣고 있어.')

    def test_sanitized_http_errors(self):
        for code, expected in [(401,'키'),(402,'크레딧'),(429,'한도')]:
            failure=urllib.error.HTTPError(BASE,code,'bad',{},io.BytesIO(b'SECRET'))
            with patch('providers.urllib.request.urlopen',side_effect=failure):
                with self.assertRaises(ValueError) as raised:request('/key','SECRET')
            self.assertIn(expected,str(raised.exception))
            self.assertNotIn('SECRET',str(raised.exception))

    def test_stream_routes_and_separates_history(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.sqlite'
            def connect():
                c=sqlite3.connect(path);c.row_factory=sqlite3.Row;return c
            with connect() as c:c.execute('CREATE TABLE memories(id INTEGER PRIMARY KEY,text TEXT)')
            self.p.local.update(provider='openrouter',model='a/text')
            self.vault.set_password(SERVICE,'local-test','test-key')
            chat=Conversation(self.account,connect,providers=self.p)
            class Stream:
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def __iter__(self):
                    yield b': OPENROUTER PROCESSING\n'
                    yield b'data: {"choices":[{"delta":{"content":"hello"},"finish_reason":null}]}\n'
                    yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n'
                    yield b'data: {"choices":[],"usage":{}}\n'
                    yield b'data: [DONE]\n'
            def finish():
                for t in threading.enumerate():
                    if t.name.endswith('(worker)'):t.join(2)
            with patch('chatgpt.urllib.request.urlopen',return_value=Stream()) as req:
                chat.start('hi');finish()
                sent=req.call_args.args[0]
                self.assertEqual(sent.full_url,BASE+'/chat/completions')
                body=json.loads(sent.data)
                self.assertEqual(body['model'],'a/text')
                self.assertIn('존댓말',body['messages'][0]['content'])
                self.assertEqual(chat.snapshot()['messages'][-1]['text'],'hello')
                self.account.access.assert_not_called()
            class Broken(Stream):
                def __iter__(self):
                    yield b'data: {"choices":[{"delta":{"content":"partial"}}]}\n'
                    yield b'data: {"error":{"code":402,"message":"SECRET"},"choices":[]}\n'
            with patch('chatgpt.urllib.request.urlopen',return_value=Broken()):
                chat.start('again');finish()
                self.assertEqual(chat.snapshot()['status'],'error')
                self.assertIn('크레딧',chat.snapshot()['error'])
                self.assertNotIn('SECRET',chat.snapshot()['error'])
                self.assertEqual([m['text'] for m in chat.snapshot()['messages'] if m['role']=='assistant'],['hello'])
            self.p.local['provider']='chatgpt'
            self.assertEqual(chat.snapshot()['messages'],[])
