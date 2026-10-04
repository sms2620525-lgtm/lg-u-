"""Production cloud login boot: no local SQLite/settings cache is created."""
import argparse,os,subprocess,sys,tempfile,time,urllib.request,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--executable');a=p.parse_args()
command=[str(Path(a.executable).resolve())] if a.executable else [sys.executable,'app.py']
with tempfile.TemporaryDirectory() as d:
 env={**os.environ,'JARVIS_DATA_DIR':d,'JARVIS_PORT':'18767'};env.pop('JARVIS_TEST_LOCAL',None)
 proc=subprocess.Popen(command+['--no-browser'],env=env)
 try:
  for _ in range(100):
   try:
    with urllib.request.urlopen('http://127.0.0.1:18767/',timeout=1) as r:
     page=r.read().decode();assert 'email-form' in page;break
   except OSError:time.sleep(.1)
  else:raise AssertionError('cloud app did not boot')
  assert not (Path(d)/'jarvis.sqlite3').exists()
  assert not (Path(d)/'chatgpt-accounts.json').exists()
  assert not (Path(d)/'voice.json').exists()
  with urllib.request.urlopen('http://127.0.0.1:18767/api/cloud/status') as r:
   state=json.load(r);assert set(state)=={'connected','email','project'}
  print('PASS: production cloud login page; no on-disk database, account metadata or voice settings')
 finally:proc.terminate();proc.wait(timeout=5)
