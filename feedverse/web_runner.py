"""Supervise a single independent AGH exploration; subprocesses survive web refresh."""
import json,os,shutil,signal,subprocess,sys,time,threading
from pathlib import Path
from .backend import Backend,PROJECT
from .data import dump,sha
from .sandbox import probe
from .web_store import Store,read_json,ACTIVE

def child_alive(pid):
    try:os.kill(pid,0);return True
    except ProcessLookupError:return False

def launch(store,eid):
    row=store.get(eid)
    if row['status'] not in ['preparing','interrupted','cancelled','failed']:return row
    run=store.path(eid);run.mkdir(parents=True,exist_ok=True)
    log=open(run/'runner.log','a')
    proc=subprocess.Popen([sys.executable,'-m','feedverse.web_runner',str(store.root),str(store.history),eid],cwd=PROJECT,stdout=log,stderr=log,start_new_session=True)
    log.close();store.update(eid,pid=proc.pid,error=None)
    threading.Thread(target=proc.wait,daemon=True).start();return store.get(eid)

def run(store,eid):
    spec=store.get(eid);folder=store.path(eid);core=folder/'core';runtime=folder/'runtime';runtime.mkdir(parents=True,exist_ok=True)
    services=[];agh_started=False;agent=None;b=None;config=runtime/'config.json'
    store.update(eid,pid=os.getpid(),error=None)
    outcome='failed';failure=None
    def invoke(action,timeout=90):
        with open(folder/'agh-service.log','a') as log:
            return subprocess.run([sys.executable,str(PROJECT/'scripts/agh_local.py'),'--runtime',str(runtime),'--config',str(config),action],cwd=PROJECT,stdout=log,stderr=log,timeout=timeout,check=True)
    def stopping():return store.get(eid)['status']=='cancelling'
    try:
        c=read_json(PROJECT/'config/agh.example.json');dump(config,c)
        probe(folder/'isolation')
        if not (core/'exploration-spec.json').exists():
            core.mkdir(parents=True,exist_ok=True)
            for name in ['public','frozen']: (core/name).symlink_to(store.history/name,target_is_directory=True)
            dump(core/'exploration-spec.json',{'id':eid,'candidate_limit':spec['candidate_limit'],'instruction':spec['instruction'],'validation_only':True,'data_manifest_sha256':sha(store.history/'frozen/manifest.json')})
            base=core/'variants/baseline';(base/'artifacts').mkdir(parents=True)
            src=store.history/'variants/baseline'
            for name in ['source','.git']:shutil.copytree(src/name,base/name)
            for name in ['config.json','checkpoint.pt','checkpoint-identity.json','identity.json']:shutil.copyfile(src/'artifacts'/name,base/'artifacts'/name)
            shutil.copyfile(src/'validation-evaluation.json',base/'validation-evaluation.json')
            (base/'score-validation').mkdir();shutil.copyfile(src/'score-validation/scores.json',base/'score-validation/scores.json')
            dump(base/'variant.json',{'name':'baseline','imported':True,'origin':'verified-20261010','description':'核验后复用的 ID embedding + GRU 基线'})
        b=Backend(core);identity=b.identity('baseline');ci=read_json(core/'variants/baseline/artifacts/checkpoint-identity.json')
        if any(ci.get(k)!=v for k,v in identity.items()) or sha(core/'variants/baseline/artifacts/checkpoint.pt')!=ci['checkpoint_sha256']:raise ValueError('Imported baseline identity mismatch')
        # Original dataset identity is rechecked before every new/resumed exploration.
        frozen=read_json(core/'exploration-spec.json')
        if frozen['candidate_limit']!=spec['candidate_limit'] or frozen['instruction']!=spec['instruction'] or frozen['data_manifest_sha256']!=b.check_data():raise ValueError('Exploration identity changed')
        if (core/'selection.json').exists():
            outcome='completed';return
        # Reconcile orphaned training jobs before the agent decides which failures to repair.
        with b.db() as db:jobs=[dict(r) for r in db.execute("SELECT * FROM jobs WHERE state IN ('queued','running')")]
        for job in jobs:
            status=b.get_job_status(job['id'])
            if status['state']=='interrupted' and job['pid']:
                try:os.killpg(job['pid'],signal.SIGTERM)
                except ProcessLookupError:pass
        store.event(eid,'lifecycle','baseline-import','lifecycle','基线身份已核验，复用已有模型',identity)
        if stopping():raise InterruptedError('Cancelled before agent startup')
        commands=[('bridge',[sys.executable,str(PROJECT/'scripts/trapi_bridge.py'),'--root',str(runtime),'--config',str(config)]),('mcp',[sys.executable,str(PROJECT/'scripts/mcp_server.py'),'--root',str(core),'--http',str(c['mcpPort'])])]
        for name,cmd in commands:
            log=open(folder/(name+'.log'),'a');p=subprocess.Popen(cmd,cwd=PROJECT,stdout=log,stderr=log);log.close();services.append(p)
        import requests
        ready=False
        for _ in range(60):
            if any(p.poll() is not None for p in services):raise RuntimeError('Local bridge/MCP failed to start; check service logs and occupied ports')
            try:
                key=(runtime/'bridge.key').read_text().strip()
                resp=requests.get(f"http://127.0.0.1:{c['bridgePort']}/v1/models",headers={'Authorization':'Bearer '+key},timeout=1)
                m=requests.post(f"http://127.0.0.1:{c['mcpPort']}/mcp",json={'jsonrpc':'2.0','id':1,'method':'tools/list'},timeout=1)
                if resp.status_code==200 and len(m.json()['result']['tools'])==10:ready=True;break
            except (OSError,requests.RequestException,ValueError,KeyError):pass
            time.sleep(.25)
        if not ready:raise RuntimeError('Local services readiness failed')
        dump(runtime/'services.json',{'bridge':'ready','mcp':'ready','agh':'starting'})
        invoke('start');agh_started=True;invoke('setup')
        dump(runtime/'services.json',{'bridge':'ready','mcp':'ready','agh':'ready'})
        if stopping():raise InterruptedError('Cancelled during preparation')
        store.update(eid,status='running')
        store.event(eid,'lifecycle','agent-start:'+str(time.time()),'lifecycle','AGH 开始真实探索',{'candidate_limit':spec['candidate_limit']})
        log=open(folder/'agent.log','a')
        agent=subprocess.Popen([str(PROJECT/'local/agh-pinned/node_modules/.bin/tsx'),str(PROJECT/'scripts/agh_session.mjs'),'explore'],cwd=PROJECT,env={**os.environ,'AGH_HOME':str(runtime/'home'),'AGNES_PROFILE':'local-dev','FEEDVERSE_AGH_RUNTIME':str(runtime),'FEEDVERSE_AGH_CONFIG':str(config)},stdout=log,stderr=log)
        log.close();cancel_sent=False;cancel_since=None
        while agent.poll() is None:
            store.ingest(eid)
            with b.db() as db:live=[r['id'] for r in db.execute("SELECT id FROM jobs WHERE state IN ('queued','running')")]
            if stopping():
                if not cancel_sent:
                    if (runtime/'exploration.json').exists():
                        try:
                            with open(folder/'cancel.log','a') as log:subprocess.run([str(PROJECT/'local/agh-pinned/node_modules/.bin/tsx'),str(PROJECT/'scripts/agh_session.mjs'),'cancel'],cwd=PROJECT,env={**os.environ,'FEEDVERSE_AGH_RUNTIME':str(runtime),'FEEDVERSE_AGH_CONFIG':str(config)},stdout=log,stderr=log,timeout=10)
                        except subprocess.TimeoutExpired:pass
                    agent.terminate();cancel_sent=True;cancel_since=time.monotonic()
                for jid in live:b.cancel(jid)
                if time.monotonic()-cancel_since>15:agent.kill()
            time.sleep(.5)
        store.ingest(eid)
        if stopping():raise InterruptedError('User cancelled exploration')
        if agent.returncode:raise RuntimeError('AGH session failed; see preserved agent and bridge receipts')
        models=[p for p in b.variants.iterdir() if p.name!='baseline']
        if len(models)!=spec['candidate_limit']:raise RuntimeError('AGH stopped before the requested candidate count was reached')
        for p in models:
            if not (p/'validation-evaluation.json').exists():raise RuntimeError('Candidate missing valid evaluation: '+p.name)
            if b.read_source(p.name)==b.read_source('baseline'):raise RuntimeError('Candidate contains no executable source change')
            log=p/'artifacts/train.log';epochs=[json.loads(x)['epoch'] for x in log.read_text().splitlines() if x.startswith('{')]
            if epochs!=[1,2,3,4,5]:raise RuntimeError('Candidate training budget was not respected')
        selection=b.select();store.event(eid,'lifecycle','selection','lifecycle','按验证冷启动 NDCG@10 冻结方案',selection)
        outcome='completed'
    except InterruptedError as exc:
        outcome='cancelled';failure=str(exc);store.update(eid,status='cancelling',error=failure)
    except Exception as exc:
        outcome='failed';failure=type(exc).__name__+': '+str(exc);store.update(eid,error=failure)
        store.event(eid,'lifecycle','failure:'+str(time.time()),'error','探索失败',{'type':type(exc).__name__,'message':str(exc)})
    finally:
        if b:
            with b.db() as db:live=[r['id'] for r in db.execute("SELECT id FROM jobs WHERE state IN ('queued','running')")]
            for jid in live:b.cancel(jid)
        if agent and agent.poll() is None:agent.kill();agent.wait()
        if agh_started:
            try:invoke('stop',30)
            except Exception:pass
        for p in services:
            if p.poll() is None:
                p.terminate()
                try:p.wait(timeout=5)
                except subprocess.TimeoutExpired:p.kill();p.wait()
        dump(runtime/'services.json',{'bridge':'stopped','mcp':'stopped','agh':'stopped'})
        store.ingest(eid)
        if store.get(eid)['status']=='cancelling':outcome='cancelled'
        store.update(eid,status=outcome,pid=None,error=failure)
        store.event(eid,'lifecycle','terminal:'+str(time.time()),'lifecycle','AGH 与训练均已停止' if outcome=='cancelled' else '本轮探索结束',{'status':outcome})

if __name__=='__main__':run(Store(sys.argv[1],sys.argv[2]),sys.argv[3])
