import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import security

class ScanTests(unittest.TestCase):
    def test_reject_shell_and_ranges(self):
        for bad in ['127.0.0.1; echo bad', '--script=all', '10.0.0.0/24', 'host.test', '', '::', '224.0.0.1', 'fe80::1%en0']:
            with self.assertRaises(ValueError): security.target_ip(bad)
    def test_ipv6_command_and_fixed_scope(self):
        args=security.command('/usr/bin/nmap','::1','/tmp/result.xml')
        self.assertIn('-6',args)
        self.assertIn('-sT',args)
        self.assertEqual(args[-1],'::1')
        self.assertNotIn('--script',args)
    def test_xml_and_open_ports(self):
        xml='<nmaprun><host><address addr="127.0.0.1"/><ports><port protocol="tcp" portid="443"><state state="open"/><service name="https" product="test"/></port></ports></host><runstats><finished exit="success"/></runstats></nmaprun>'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'test.xml';p.write_text(xml)
            data=security.parse_xml(p)
            self.assertEqual(data[0]['ports'][0]['port'],443)
            self.assertEqual(data[0]['ports'][0]['state'],'open')
            p.write_text('<nmaprun/>')
            with self.assertRaises(ValueError): security.parse_xml(p)
    def test_missing_nmap(self):
        with tempfile.TemporaryDirectory() as d, patch('security.find_nmap',return_value=None):
            with self.assertRaises(ValueError): security.Scanner(d).start('127.0.0.1')

class APITests(unittest.TestCase):
    @classmethod
def setUpClass(cls):
    cls.tmp = tempfile.TemporaryDirectory()
    os.environ['JARVIS_DATA_DIR'] = cls.tmp.name
    import app
    cls.app = app
    cls.app.auth.set_password('password1234')
    cls.session = cls.app.auth.issue_session()
    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
    def request(self, path, payload=None, valid=True):
    h = object.__new__(self.app.Handler)
    h.path = path
    h.requestline = f"{'GET' if payload is None else 'POST'} {path} HTTP/1.1"
    h.client_address = ('127.0.0.1', 12345)
    h.server = type('Server', (), {'server_port': self.app.PORT, 'shutdown': lambda *a, **k: None})()

    data = json.dumps(payload).encode() if payload is not None else b''
    h.rfile = io.BytesIO(data)

    # 세션 쿠키를 실제 브라우저처럼 넣어주면 /api/memories, /api/delete 등 인증 경로 통과
    session = self.app.auth.issue_session()
    h.headers = {
        'Host': f'127.0.0.1:{self.app.PORT}',
        'Origin': self.app.ORIGIN,
        'X-Jarvis-Token': self.app.TOKEN if valid else 'bad',
        'Content-Length': str(len(data)),
        'Cookie': f'jarvis_session={session}',
    }

    result = []
    h.send = lambda *args: result.append(args)
    (h.do_GET if payload is None else h.do_POST)()
    return result[0] if result else (401, {})
    def test_memory_and_csrf(self):
        self.assertEqual(self.request('/api/memories',{'text':'hello'})[0],200)
        rows=self.request('/api/memories')[1]['memories'];self.assertEqual(len(rows),1)
        self.assertEqual(self.request('/api/delete',{'id':rows[0]['id']},False)[0],403)
        self.assertEqual(self.request('/api/delete',{'id':rows[0]['id']})[0],200)
    def test_scan_validation(self):
        self.assertEqual(self.request('/api/scan',{'target':'127.0.0.1;id'})[0],400)
    def test_assets(self):
        for path in ['/','/cyber.js','/cyber.css']:
            self.assertEqual(self.request(path)[0],200)

if __name__=='__main__': unittest.main()
