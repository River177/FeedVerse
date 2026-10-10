import json, os, subprocess, sys, tempfile
from pathlib import Path

def policy(read,write,network=False):
    # Deny regular file contents outside explicit inputs and system/runtime libraries. Directory traversal metadata remains available to the loader; protected contents do not.
    read=[Path(p).resolve() for p in read]+[Path(sys.prefix).resolve(), Path("/System"), Path("/usr"), Path("/Library"), Path("/private/etc"), Path("/dev")]
    def sub(p): return '(subpath '+json.dumps(str(p))+')'
    exceptions=' '.join('(require-not '+sub(p)+')' for p in read)
    writes=' '.join('(require-not '+sub(Path(p).resolve())+')' for p in write+[Path('/dev')])
    return '(version 1)(allow default)'+('' if network else '(deny network*)')+'(deny file-read-data (require-all (vnode-type REGULAR-FILE) '+exceptions+'))(deny file-write* (require-all '+writes+'))(deny signal)'

def command(source,public,artifacts,mode,inputs):
    artifacts=Path(artifacts); tmp=artifacts/'tmp'; tmp.mkdir(exist_ok=True)
    profile=policy([source.parent,public,artifacts],[artifacts,tmp])
    (artifacts/'sandbox.sb').write_text(profile)
    return ['/usr/bin/sandbox-exec','-f',str(artifacts/'sandbox.sb'),sys.executable,'-I','-B',str(source.parent/'worker.py'),mode,str(source),str(public),str(artifacts),str(inputs)]

def probe(root):
    root=Path(root).resolve(); allowed=root/'probe'; allowed.mkdir(parents=True,exist_ok=True)
    secret=root/'protected-probe.txt'; secret.write_text('hidden')
    script=allowed/'test.py'; script.write_text('''import json, pathlib, socket, torch
root=pathlib.Path(__file__).parent.parent
results={}
for name,fn in [('read',lambda:(root/'protected-probe.txt').read_text()),('write',lambda:(root/'protected-probe.txt').write_text('bad')),('network',lambda:socket.create_connection(('127.0.0.1',5173),timeout=1))]:
 try: fn(); results[name]=False
 except PermissionError: results[name]=True
print(json.dumps({'blocked':results,'torch':torch.ones(1).item()}))
''')
    profile=policy([allowed],[allowed]); env={**os.environ,'TMPDIR':str(allowed),'KMP_USE_SHM':'0','PYTHONDONTWRITEBYTECODE':'1'}
    result=subprocess.run(['/usr/bin/sandbox-exec','-p',profile,sys.executable,'-I',str(script)],cwd=allowed,env=env,capture_output=True,text=True)
    if result.returncode: raise RuntimeError('Sandbox probe failed: '+result.stderr)
    receipt=json.loads(result.stdout); assert all(receipt['blocked'].values()) and secret.read_text()=='hidden'
    return receipt
