"""Run the same real HTTP auth lifecycle against source and the packaged app."""
import argparse
import http.cookiejar
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--executable')
args = parser.parse_args()
command = [str(Path(args.executable).resolve())] if args.executable else [sys.executable, 'app.py']
base = 'http://127.0.0.1:18765'
with tempfile.TemporaryDirectory() as directory:
    env = {**os.environ, 'JARVIS_DATA_DIR': directory, 'JARVIS_PORT': '18765'}
    cookies = http.cookiejar.CookieJar()
    client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    process = None
    token = ''
    def start():
        global process, token
        process = subprocess.Popen(command + ['--no-browser'], env=env)
        for _ in range(100):
            if process.poll() is not None:
                raise AssertionError(f'App exited: {process.returncode}')
            try:
                with client.open(base, timeout=1) as response:
                    html = response.read().decode()
                    token = re.search("const token='([^']+)'", html)[1]
                    return response.url, html
            except OSError:
                time.sleep(.1)
        raise AssertionError('App did not start')
    def call(path, data=None, expected=200):
        request = urllib.request.Request(base + path, None if data is None else json.dumps(data).encode(),
            headers={'Content-Type': 'application/json', 'Origin': base, 'X-Jarvis-Token': token})
        try:
            response = client.open(request, timeout=10)
        except urllib.error.HTTPError as e:
            response = e
        with response:
            text = response.read().decode()
            assert response.code == expected, (path, response.code, text)
            return json.loads(text) if response.headers.get_content_type() == 'application/json' else text
    try:
        url, html = start()
        assert url.endswith('/setup') and 'JARVIS' in html
        call('/api/memories', expected=401)
        call('/api/setup', {'password': 'testpass123'})
        assert 'phone-enable' in call('/')
        for asset in ('/cyber.js', '/cyber.css'):
            assert call(asset)
        call('/api/memories', {'text': 'preserve after restart'})
        call('/api/logout', {})
        assert 'current-password' in call('/')
        call('/api/memories', expected=401)
        call('/api/login', {'password': None}, expected=401)
        call('/api/login', {'password': 'wrong'}, expected=401)
        call('/api/login', {'password': 'testpass123'})
        assert call('/api/memories')['memories'][0]['text'] == 'preserve after restart'
        assert not call('/api/phone')['enabled']
        call('/api/logout', {})
        process.terminate(); process.wait(timeout=5)
        url, html = start()
        assert url.endswith('/login')
        call('/api/login', {'password': 'testpass123'})
        rows = call('/api/memories')['memories']
        assert len(rows) == 1 and rows[0]['text'] == 'preserve after restart'
        call('/api/delete', {'id': rows[0]['id']})
        assert not call('/api/memories')['memories']
        print('PASS: setup, logout/login, bad input, assets, restart persistence, memory CRUD')
    finally:
        if process and process.poll() is None:
            process.terminate(); process.wait(timeout=5)
