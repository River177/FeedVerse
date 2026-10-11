"""One-command loopback API/Vite launcher. No model calls until an exploration starts."""
import json,os,signal,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
candidates=[os.getenv('FEEDVERSE_PYTHON'),str(ROOT/'.venv/bin/python'),str(Path.home()/'miniforge3/bin/python3.13'),sys.executable]
python=None
for candidate in candidates:
    if candidate and Path(candidate).exists() and subprocess.run([candidate,'-c','import torch,fastapi,uvicorn,numpy'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:python=candidate;break
if not python:raise SystemExit('Install requirements-core.txt and requirements-web.txt; set FEEDVERSE_PYTHON to that interpreter.')
subprocess.run([python,'-c','from feedverse.sandbox import probe; from pathlib import Path; print("Sandbox verified:",probe(Path("local/web-boot")))'],cwd=ROOT,check=True)
owned=[]
local_http=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def get(url):
    try:
        with local_http.open(url,timeout=1) as r:return r.read().decode()
    except Exception:return None
try:
    existing=get('http://127.0.0.1:18779/api/health')
    if existing:
        if json.loads(existing).get('product')!='FeedVerse':raise RuntimeError('API port is occupied by another service')
    else:
        owned.append(subprocess.Popen([python,'-m','uvicorn','feedverse.web_api:app','--host','127.0.0.1','--port','18779'],cwd=ROOT,start_new_session=True))
        for _ in range(80):
            if owned[0].poll() is not None:raise RuntimeError('API startup failed')
            if get('http://127.0.0.1:18779/api/health'):break
            time.sleep(.25)
        else:raise RuntimeError('API readiness timeout')
    page=get('http://127.0.0.1:5173/')
    if page and 'FeedVerse' not in page:raise RuntimeError('Frontend port 5173 is occupied by another project')
    if not page:owned.append(subprocess.Popen(['npm','run','dev','--','--strictPort'],cwd=ROOT,start_new_session=True))
    print('FeedVerse: http://127.0.0.1:5173/ · API: http://127.0.0.1:18779',flush=True)
    while all(p.poll() is None for p in owned):time.sleep(1)
except KeyboardInterrupt:pass
finally:
    signal.signal(signal.SIGINT,signal.SIG_IGN)
    if not existing:
        # Ask the independent manager to clean its own AGH/bridge/MCP children before stopping this API.
        health=get('http://127.0.0.1:18779/api/health')
        active=json.loads(health).get('active') if health else None
        if active:
            try:local_http.open(urllib.request.Request(f'http://127.0.0.1:18779/api/explorations/{active}/cancel',data=b'',method='POST'),timeout=2).close()
            except Exception:pass
            for _ in range(45):
                result=get(f'http://127.0.0.1:18779/api/experiments/{active}')
                if not result or json.loads(result)['status'] not in ['preparing','running','cancelling']:break
                time.sleep(1)
    for p in reversed(owned):
        if p.poll() is None:
            os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
