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
        # Wait for server to start
        for attempt in range(50):
            try:
                html = urllib.request.urlopen(base, timeout=1).read().decode()
                break
            except OSError:
                time.sleep(.1)
        else:
            raise AssertionError('Server did not start')

        token = re.search("const token='([^']+)'", html)[1]

        # Setup password and get session cookie
        setup_req = urllib.request.Request(
            base + '/api/setup',
            data=json.dumps({'password': 'testpass123'}).encode(),
            headers={
                'Content-Type': 'application/json',
                'Origin': base,
                'X-Jarvis-Token': token,
            },
            method='POST',
        )
        with urllib.request.urlopen(setup_req, timeout=10) as response:
            setup_result = json.loads(response.read().decode())
            if not setup_result.get('ok'):
                raise AssertionError(f"Setup failed: {setup_result}")
            # Extract session cookie from Set-Cookie header
            set_cookie = response.headers.get('Set-Cookie')
            if not set_cookie:
                raise AssertionError('No Set-Cookie header in setup response')
            session_cookie = set_cookie.split(';')[0]

        # Helper function for authenticated requests
        def authed_request(method, path, data=None):
            url = base + path
            body = json.dumps(data).encode() if data else None
            req = urllib.request.Request(
                url,
                data=body,
                headers={
                    'Content-Type': 'application/json',
                    'Origin': base,
                    'X-Jarvis-Token': token,
                    'Cookie': session_cookie,
                },
                method=method,
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                text = response.read().decode()
                return json.loads(text) if text else {}

        # Post a memory
        post_result = authed_request('POST', '/api/memories', {'text': 'local integration'})
        if not post_result.get('ok'):
            raise AssertionError(f"POST /api/memories failed: {post_result}")

        # Verify memory was stored
        memories = authed_request('GET', '/api/memories')
        if not memories.get('memories') or memories['memories'][0]['text'] != 'local integration':
            raise AssertionError(f"Memory check failed: {memories}")

        # Check phone status
        phone_status = authed_request('GET', '/api/phone')
        if phone_status.get('enabled') is not False:
            raise AssertionError(f"Phone status check failed: {phone_status}")

        # Check static file
        static = urllib.request.urlopen(base + '/cyber.js', timeout=10)
        if static.status != 200:
            raise AssertionError(f"Static file check failed with status {static.status}")

        print('PASS: local HTTP memory, static UI, Bluetooth idle status')
    except urllib.error.HTTPError as e:
        print(f'HTTP Error {e.code}: {e.reason}')
        raise
    finally:
        process.terminate()
        process.wait(timeout=5)
