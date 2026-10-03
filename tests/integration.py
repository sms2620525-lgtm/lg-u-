"""CI loopback integration; does not scan any external host."""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request


with tempfile.TemporaryDirectory() as directory:
    process = subprocess.Popen(
        [sys.executable, 'app.py', '--no-browser'],
        env={**os.environ, 'JARVIS_DATA_DIR': directory, 'JARVIS_PORT': '18765'},
    )
    base = 'http://127.0.0.1:18765'
    try:
        for attempt in range(50):
            try:
                html = urllib.request.urlopen(base, timeout=1).read().decode()
                break
            except OSError:
                time.sleep(.1)
        else:
            raise AssertionError('Server did not start')

        token = re.search("const token='([^']+)'", html)[1]

        def request_json(url, payload=None, headers=None, method=None):
            body = None if payload is None else json.dumps(payload).encode()
            headers = headers or {}
            req = urllib.request.Request(url, data=body, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=10) as response:
                text = response.read().decode()
                return json.loads(text) if text else {}

        # Set a password and keep the session cookie returned by the server.
        setup_headers = {'Origin': base, 'X-Jarvis-Token': token}
        setup_response = request_json(base + '/api/setup', {'password': 'testpass123'}, setup_headers, 'POST')
        if setup_response.get('ok') is not True:
            raise AssertionError(f"setup failed: {setup_response}")

        session_cookie = None
        # We need the raw response headers to read Set-Cookie, so use the lower-level opener.
        setup_req = urllib.request.Request(
            base + '/api/setup',
            data=json.dumps({'password': 'testpass123'}).encode(),
            headers={'Content-Type': 'application/json', **setup_headers},
            method='POST',
        )
        with urllib.request.urlopen(setup_req, timeout=10) as response:
            session_cookie = response.headers.get('Set-Cookie')
            if not session_cookie:
                raise AssertionError('No session cookie returned from /api/setup')
            session_cookie = session_cookie.split(';', 1)[0]

        auth_headers = {'Origin': base, 'X-Jarvis-Token': token, 'Cookie': session_cookie}

        request_json(base + '/api/memories', {'text': 'local integration'}, auth_headers, 'POST')
        memories = request_json(base + '/api/memories', headers={'Cookie': session_cookie}, method='GET')
        assert memories['memories'][0]['text'] == 'local integration'

        phone_status = request_json(base + '/api/phone', headers={'Cookie': session_cookie}, method='GET')
        assert phone_status['enabled'] is False

        static = urllib.request.urlopen(base + '/cyber.js', timeout=10)
        assert static.status == 200
        print('PASS: local HTTP memory, static UI, Bluetooth idle status')
    except urllib.error.HTTPError as e:
        print(f'HTTP Error {e.code}: {e.reason}')
        raise
    finally:
        process.terminate()
        process.wait(timeout=5)
