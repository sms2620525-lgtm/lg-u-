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
            return json.load(urllib.request.urlopen(request,timeout=3))
        local={'Origin':base,'X-Jarvis-Token':token}
        pin=post(base+'/api/phone/enable',{},local)['pin']
        remote=post('http://127.0.0.1:8766/pair',{'pin':pin},{})['token']
        post('http://127.0.0.1:8766/motion',{'pitch':25,'roll':-12},{'Authorization':'Bearer '+remote})
        state=json.load(urllib.request.urlopen(base+'/api/phone'))
        assert state['connected'] and state['pitch']==25 and state['roll']==-12
        post(base+'/api/phone/disable',{},local)
        assert not json.load(urllib.request.urlopen(base+'/api/phone'))['enabled']
        print('PASS: real HTTP pairing, motion delivery, disconnect')
    finally:
        process.terminate();process.wait(timeout=5)
