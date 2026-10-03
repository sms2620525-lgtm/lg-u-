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

with tempfile.TemporaryDirectory() as directory:
    process=subprocess.Popen([sys.executable,'app.py','--no-browser'],env={**os.environ,'JARVIS_DATA_DIR':directory,'JARVIS_PORT':'18765'})
    base='http://127.0.0.1:18765'
    try:
        for attempt in range(50):
            try:
                html=urllib.request.urlopen(base,timeout=1).read().decode();break
            except OSError:
                time.sleep(.1)
        else: raise AssertionError('Server did not start')
        token=re.search("const token='([^']+)'",html)[1]
        def post(url,data,headers):
            request=urllib.request.Request(url,json.dumps(data).encode(),headers={'Content-Type':'application/json',**headers})
            return json.load(urllib.request.urlopen(request,timeout=10))
        local={'Origin':base,'X-Jarvis-Token':token}
        post(base+'/api/memories',{'text':'local integration'},local)
        assert json.load(urllib.request.urlopen(base+'/api/memories'))['memories'][0]['text']=='local integration'
        assert not json.load(urllib.request.urlopen(base+'/api/phone'))['enabled']
        assert urllib.request.urlopen(base+'/cyber.js').status==200
        print('PASS: local HTTP memory, static UI, Bluetooth idle status')
    finally:
        process.terminate();process.wait(timeout=5)
