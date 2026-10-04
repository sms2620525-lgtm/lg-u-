import json
import time
import unittest
from unittest.mock import Mock, patch
from cloud import Cloud, RuntimeAuth, URL

class Vault:
    def __init__(self): self.data={}
    def get_password(self,s,k): return self.data.get((s,k))
    def set_password(self,s,k,v): self.data[s,k]=v
    def delete_password(self,s,k): self.data.pop((s,k),None)

class CloudTests(unittest.TestCase):
    def setUp(self):
        self.c=Cloud(Vault())
        self.c.session={'access_token':'private','refresh_token':'refresh','expires_at':time.time()+3600,'user':{'id':'user-a','email':'a@example.com'}}
        self.c.device='device'

    def test_owner_filters_and_no_secret_in_status(self):
        self.c.request=Mock(return_value=[])
        self.c.records('memory')
        path=self.c.request.call_args.args[0]
        self.assertIn('user_id=eq.user-a',path)
        self.assertNotIn('private',json.dumps(self.c.status()))
        self.c.put('memory',{'text':'hello'})
        self.assertEqual(self.c.request.call_args.args[1]['user_id'],'user-a')

    def test_no_session_never_saves(self):
        self.c.session=None
        with self.assertRaises(ValueError): self.c.put('memory',{'text':'x'})

    def test_link_origin_checked_before_exchange(self):
        self.c.pending_email='a@example.com';self.c.request=Mock()
        with self.assertRaises(ValueError): self.c.verify('https://evil.example/auth/v1/verify?token=x&type=magiclink')
        self.c.request.assert_not_called()

    def test_correct_link_exchange_and_identity_check(self):
        self.c.pending_email='a@example.com'
        self.c.request=Mock(side_effect=[{'access_token':'new','refresh_token':'new-refresh'}, {'id':'user-a','email':'a@example.com'}])
        self.c.verify(URL+'/auth/v1/verify?token=hash&type=magiclink')
        self.assertEqual(self.c.request.call_args_list[0].args[1],{'token_hash':'hash','type':'email'})
        self.assertEqual(self.c.session['access_token'],'new')

    def test_wrong_email_rejected(self):
        self.c.pending_email='a@example.com'
        self.c.request=Mock(return_value={'id':'other','email':'other@example.com'})
        with self.assertRaises(ValueError):self.c.accept({'access_token':'bad','refresh_token':'bad'})
        self.assertEqual(self.c.session['access_token'],'private')

    def test_failed_write_not_reported_as_success(self):
        self.c.request=Mock(side_effect=ValueError('offline'))
        with self.assertRaisesRegex(ValueError,'offline'): self.c.put('memory',{'text':'x'})

    def test_runtime_session_does_not_survive_restart(self):
        a=RuntimeAuth();token=a.issue_session()
        self.assertTrue(a.verify_session(token))
        self.assertFalse(RuntimeAuth().verify_session(token))
