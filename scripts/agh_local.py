"""Start a pinned local AGH under a filesystem sandbox; trusted MCP stays outside."""
import sys,json,os,subprocess,tempfile,argparse,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from feedverse.sandbox import policy
from feedverse.data import dump,sha
ROOT=Path(__file__).resolve().parents[1]; source=ROOT/'local/agh-pinned'; run=ROOT/'local/agh-runtime'; home=run/'home'; workspace=run/'workspace'
p=argparse.ArgumentParser(); p.add_argument('--config',default=str(ROOT/'config/agh.example.json')); p.add_argument('action',choices=['start','stop','setup','explore']); args=p.parse_args()
for d in [home,workspace]: d.mkdir(parents=True,exist_ok=True)
node=Path(subprocess.check_output(['which','node'],text=True).strip()).resolve()
env={**os.environ,'FEEDVERSE_AGH_CONFIG':str(Path(args.config).resolve()),'AGH_HOME':str(home),'AGNES_PROFILE':'local-dev','TMPDIR':tempfile.gettempdir(),'AGNES_MCP_ALLOW_LOOPBACK_HTTP':'1','AGNES_RESOURCE_MCP_POLICY':json.dumps({'localDaemon':True,'allowLoopbackHttp':True,'allowedExecutables':[]})}
if args.action in ['start','stop']:
    sb=policy([source,home,workspace,node.parent.parent,Path('/opt/homebrew'),Path(tempfile.gettempdir())],[home,workspace,Path(tempfile.gettempdir())],network=True)
    (run/'sandbox.sb').write_text(sb.replace('(deny signal)',''))
    cmd=['/usr/bin/sandbox-exec','-f',str(run/'sandbox.sb'),str(node),str(source/'packages/cli/dist/local/agnes.mjs'),'daemon',args.action]
else:
    cmd=[str(source/'node_modules/.bin/tsx'),str(ROOT/'scripts/agh_session.mjs'),args.action]
subprocess.run(cmd,cwd=workspace,env=env,check=True)
