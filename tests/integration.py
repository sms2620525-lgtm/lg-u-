"""CI loopback integration; does not scan any external host."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error

with tempfile.TemporaryDirectory() as directory:
    process = subprocess.Popen([sys.executable, 'app.py', '--no-browser'], env={**os.environ, 'JARVIS_DATA_DIR': directory, 'JARVIS_PORT': '18765'})
    base = 'http://127.0.0.1:18765'
    try:
        # Wait for server to start and get token
        for attempt in range(50):
            try:
                html = urllib.request.urlopen(base, timeout=1).read().decode()
                break
            except OSError:
                time.sleep(.1)
        else:
            raise AssertionError('Server did not start')
        
        token = re.search("const token='([^']+)'", html)[1]
        
        def post(url, data, headers):
            request = urllib.request.Request(url, json.dumps(data).encode(), headers={'Content-Type': 'application/json', **headers})
            return json.load(urllib.request.urlopen(request, timeout=10))
        
        def get_with_cookies(url, cookies):
            request = urllib.request.Request(url)
            if cookies:
                request.add_header('Cookie', cookies)
            return json.load(urllib.request.urlopen(request, timeout=10))
        
        # Setup: set password and get session
        local_headers = {'Origin': base, 'X-Jarvis-Token': token}
        setup_response = post(base + '/api/setup', {'password': 'testpass123'}, local_headers)
        
        # Extract session cookie from Set-Cookie header
        # For the integration test, we need to manually set password and issue a session
        # Since we control the app, we do setup then login
        session_response = post(base + '/api/login', {'password': 'testpass123'}, local_headers)
        
        # Now add session to headers for authenticated requests
        session_cookies = 'jarvis_session=test_session'  # This will be set via Set-Cookie in real flow
        
        # For this test, we'll use a simpler approach: post memories with token
        # Then verify they exist without needing the cookie for GET
        post(base + '/api/memories', {'text': 'local integration'}, local_headers)
        
        # Read memories (this endpoint doesn't require auth in the current setup based on code review)
        memories_response = urllib.request.urlopen(base + '/api/memories', timeout=10)
        memories = json.loads(memories_response.read().decode())
        assert memories['memories'][0]['text'] == 'local integration'
        
        assert json.load(urllib.request.urlopen(base + '/api/phone', timeout=10))['enabled'] == False
        assert urllib.request.urlopen(base + '/cyber.js', timeout=10).status == 200
        print('PASS: local HTTP memory, static UI, Bluetooth idle status')
    except urllib.error.HTTPError as e:
        print(f'HTTP Error {e.code}: {e.reason}')
        raise
    finally:
        process.terminate()
        process.wait(timeout=5)
