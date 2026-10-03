from pathlib import Path
import tempfile
import time
import unittest
import auth

class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.a=auth.Auth(Path(self.tmp.name)/'test.sqlite3')
    def tearDown(self):
        self.tmp.cleanup()
    def test_no_password_initially(self):
        self.assertFalse(self.a.has_password())
        with self.assertRaises(auth.AuthError): self.a.verify_password('whatever123')
    def test_set_and_verify_password(self):
        self.a.set_password('correct-horse-battery')
        self.assertTrue(self.a.has_password())
        self.assertTrue(self.a.verify_password('correct-horse-battery'))
        self.assertFalse(self.a.verify_password('wrong-password'))
    def test_short_password_rejected(self):
        with self.assertRaises(auth.AuthError): self.a.set_password('short')
    def test_lockout_after_max_attempts(self):
        self.a.set_password('correct-horse-battery')
        for _ in range(auth.MAX_ATTEMPTS):
            self.assertFalse(self.a.verify_password('wrong'))
        with self.assertRaises(auth.AuthError): self.a.verify_password('correct-horse-battery')
    def test_session_lifecycle(self):
        token=self.a.issue_session()
        self.assertTrue(self.a.verify_session(token))
        self.a.revoke_session(token)
        self.assertFalse(self.a.verify_session(token))
    def test_unknown_session_rejected(self):
        self.assertFalse(self.a.verify_session('not-a-real-token'))
        self.assertFalse(self.a.verify_session(None))
    def test_changing_password_drops_sessions(self):
        self.a.set_password('correct-horse-battery')
        token=self.a.issue_session()
        self.a.set_password('new-correct-horse')
        self.assertFalse(self.a.verify_session(token))

class CookieTests(unittest.TestCase):
    def test_read_cookie(self):
        self.assertEqual(auth.read_cookie('a=1; jarvis_session=abc123; b=2','jarvis_session'),'abc123')
        self.assertIsNone(auth.read_cookie('a=1; b=2','jarvis_session'))
        self.assertIsNone(auth.read_cookie(None,'jarvis_session'))

if __name__=='__main__':
    unittest.main()
