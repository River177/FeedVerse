"""Start a pinned local AGH under a filesystem sandbox; trusted MCP stays outside."""
import sys,json,os,subprocess,tempfile,argparse,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from feedverse.sandbox import policy
from feedverse.data import dump,sha
ROOT=Path(__file__).resolve().parents[1]; source=ROOT/'local/agh-pinned'; run=ROOT/'local/agh-runtime'; home=run/'home'; workspace=run/'workspace'
p=argparse.ArgumentParser(); p.add_argument('--runtime'); p.add_argument('--config',default=str(ROOT/'config/agh.example.json')); p.add_argument('action',choices=['start','stop','setup','explore']); args=p.parse_args()
if args.runtime:
    run=Path(args.runtime).resolve(); home=run/'home'; workspace=run/'workspace'
for d in [home,workspace]: d.mkdir(parents=True,exist_ok=True)
node=Path(subprocess.check_output(['which','node'],text=True).strip()).resolve()
env={**os.environ,'FEEDVERSE_AGH_RUNTIME':str(run),'FEEDVERSE_AGH_CONFIG':str(Path(args.config).resolve()),'AGH_HOME':str(home),'AGNES_PROFILE':'local-dev','TMPDIR':tempfile.gettempdir(),'AGNES_MCP_ALLOW_LOOPBACK_HTTP':'1','AGNES_RESOURCE_MCP_POLICY':json.dumps({'localDaemon':True,'allowLoopbackHttp':True,'allowedExecutables':[]})}
if args.action in ['start','stop']:
    digest=hashlib.sha256(str((home/'data').resolve()).encode()).hexdigest()[:32]
    socket_dir=Path('/tmp').resolve()/f'agnes-{os.geteuid()}-{digest}'
    if socket_dir.is_symlink(): raise RuntimeError('Short socket directory is a symlink')
    socket_dir.mkdir(mode=0o700,exist_ok=True)
    st=socket_dir.stat()
    if st.st_uid!=os.geteuid() or st.st_mode & 0o7777 != 0o700: raise RuntimeError('Unsafe short socket directory')
    sb=policy([source,home,workspace,node.parent.parent,Path('/opt/homebrew'),Path(tempfile.gettempdir()),socket_dir],[home,workspace,Path(tempfile.gettempdir()),socket_dir],network=True)
    (run/'sandbox.sb').write_text(sb.replace('(deny signal)',''))
    cmd=['/usr/bin/sandbox-exec','-f',str(run/'sandbox.sb'),str(node),str(source/'packages/cli/dist/local/agnes.mjs'),'daemon',args.action]
else:
    cmd=[str(source/'node_modules/.bin/tsx'),str(ROOT/'scripts/agh_session.mjs'),args.action]
subprocess.run(cmd,cwd=workspace,env=env,check=True)
