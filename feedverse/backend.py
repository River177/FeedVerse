import hashlib, json, os, re, shutil, signal, sqlite3, subprocess, sys, time, uuid
from contextlib import contextmanager
import threading
from pathlib import Path
from .data import dump,sha,prepare
from .evaluation import metrics,rankings
from .sandbox import command,probe

PROJECT=Path(__file__).resolve().parent.parent
DEFAULT_ROOT=PROJECT/'local/core'
CONFIG={'seed':42,'device':'cpu','batch_size':128,'epochs':5,'threads':6}

class Backend:
    def __init__(self,root=DEFAULT_ROOT):
        self.root=Path(root).resolve(); self.root.mkdir(parents=True,exist_ok=True)
        self.exploration=json.loads((self.root/'exploration-spec.json').read_text()) if (self.root/'exploration-spec.json').exists() else None
        self.public=self.root/'public'; self.frozen=self.root/'frozen'; self.variants=self.root/'variants'; self.variants.mkdir(exist_ok=True)
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, variant TEXT, identity TEXT, state TEXT, pid INTEGER, created REAL, finished REAL, error TEXT)')
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.root/'state.sqlite',timeout=30); db.row_factory=sqlite3.Row
        try:
            with db: yield db
        finally: db.close()
    def check_data(self):
        m=json.loads((self.frozen/'manifest.json').read_text())
        for rel,h in m['outputs'].items():
            if sha(self.root/rel)!=h: raise ValueError('Frozen file changed: '+rel)
        return sha(self.frozen/'manifest.json')
    def path(self,name):
        if not re.fullmatch('[a-z][a-z0-9_-]{0,47}',name): raise ValueError('Invalid variant name')
        p=self.variants/name
        if p.is_symlink(): raise ValueError('Symlink variant rejected')
        return p
    def initialize(self,raw):
        receipt=probe(self.root/'isolation'); dump(self.root/'isolation-receipt.json',receipt)
        manifest=prepare(raw,self.root)
        if not self.path('baseline').exists(): self.create_variant('baseline',None)
        return {k:v for k,v in manifest.items() if k not in ['sample_ids','outputs']}
    def inspect_dataset(self):
        m=json.loads((self.frozen/'manifest.json').read_text())
        # Deliberately no heldout results/counts or file paths in agent feedback.
        train=json.loads((self.public/'train.json').read_text()); valid=json.loads((self.public/'validation-input.json').read_text())
        import statistics
        return {'protocol':m['protocol'],'train':len(train),'validation':len(valid),'validation_cold_positives':m['cold_positive_counts']['validation'],'history_length_mean':statistics.mean(len(r['history']) for r in train),'candidate_length_mean':statistics.mean(len(r['candidates']) for r in valid),'features':'title, abstract, category, 128-dimensional training-fit TF-IDF/SVD; features.npz ids and vectors','model_contract':'build(public_path, config) returns torch.nn.Module with fit(rows, artifact_path), score(rows) -> scores aligned to candidates; rows: id,user,time,history,candidates; training also has positive','baseline_source':self.read_source('baseline')}
    def create_variant(self,name,base='baseline',description=None):
        if description is not None and (not isinstance(description,str) or len(description)>1000): raise ValueError('Invalid model description')
        p=self.path(name)
        if p.exists(): raise ValueError('Variant already exists')
        if name!='baseline':
            if (self.root/'selection.json').exists(): raise ValueError('Exploration already frozen')
            if self.exploration and name not in ['candidate_'+str(i+1) for i in range(self.exploration['candidate_limit'])]: raise ValueError('Candidate ID outside frozen exploration')
            if len([v for v in self.variants.iterdir() if v.name!='baseline'])>=(self.exploration['candidate_limit'] if self.exploration else 3): raise ValueError('Three-candidate limit reached')
        source=PROJECT/'feedverse/model.py' if base is None else self.path(base)/'source/model.py'
        (p/'source').mkdir(parents=True); (p/'artifacts').mkdir()
        shutil.copyfile(source,p/'source/model.py'); shutil.copyfile(PROJECT/'feedverse/worker.py',p/'source/worker.py')
        dump(p/'artifacts/config.json',CONFIG)
        self.git(p,['init','-q']); self.git(p,['checkout','-q','-b','codex/'+name]); self.git(p,['add','source']); self.git(p,['-c','user.name=FeedVerse','-c','user.email=feedverse@localhost','commit','-qm','Initial model snapshot'])
        dump(p/'variant.json',{'name':name,'base':base,'created':time.time(),'description':description})
        return {'variant':name,'source':self.read_source(name)}
    def git(self,p,args): return subprocess.check_output(['git','-C',str(p),*args],text=True).strip()
    def read_source(self,variant): return (self.path(variant)/'source/model.py').read_text()
    def patch_source(self,variant,source):
        if variant=='baseline': raise ValueError('Baseline is immutable')
        if (self.root/'selection.json').exists(): raise ValueError('Selection frozen')
        if len(source)>100000: raise ValueError('Source too large')
        p=self.path(variant)
        with self.db() as db:
            if db.execute("SELECT 1 FROM jobs WHERE variant=? AND state IN ('queued','running')",(variant,)).fetchone(): raise ValueError('Job still running')
            if db.execute("SELECT 1 FROM jobs WHERE variant=? AND state='completed'",(variant,)).fetchone() and ((p/'validation-evaluation.json').exists() or not (p/'validation-failure.json').exists()): raise ValueError('Validated candidate is frozen; repair only failed training or evaluation')
        compile(source,'model.py','exec'); (p/'source/model.py').write_text(source)
        self.git(p,['add','source/model.py']); self.git(p,['-c','user.name=FeedVerse','-c','user.email=feedverse@localhost','commit','-qm','Candidate code edit','--allow-empty'])
        return {'variant':variant,'source_sha256':sha(p/'source/model.py'),'diff':self.git(p,['diff','HEAD~1','HEAD','--','source/model.py'])}
    def identity(self,variant):
        p=self.path(variant)
        return {'variant':variant,'source_sha256':sha(p/'source/model.py'),'worker_sha256':sha(p/'source/worker.py'),'config_sha256':sha(p/'artifacts/config.json'),'data_manifest_sha256':self.check_data(),'source_commit':self.git(p,['rev-parse','HEAD'])}
    def train_variant(self,variant):
        if variant=='baseline' and self.exploration: raise ValueError('Imported baseline is read-only; no retraining')
        p=self.path(variant); ident=self.identity(variant); identity=json.dumps(ident,sort_keys=True)
        with self.db() as db:
            prior=db.execute("SELECT * FROM jobs WHERE variant=? AND identity=? AND state IN ('queued','running','completed') ORDER BY created DESC LIMIT 1",(variant,identity)).fetchone()
            if prior: return self.get_job_status(prior['id'])
            if db.execute("SELECT 1 FROM jobs WHERE state IN ('queued','running') AND variant<>?",(variant,)).fetchone(): raise ValueError('One training worker is already active')
            previous=db.execute('SELECT * FROM jobs WHERE variant=? ORDER BY created DESC LIMIT 1',(variant,)).fetchone()
            if previous:
                archive=p/'attempts'/previous['id']; archive.mkdir(parents=True,exist_ok=True)
                for f in (p/'artifacts').iterdir():
                    if f.is_file(): shutil.copyfile(f,archive/f.name)
                dump(archive/'job.json',dict(previous))
            jid=uuid.uuid4().hex
            db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)',(jid,variant,identity,'queued',None,time.time(),None,None))
        dump(p/'artifacts/identity.json',ident)
        env={**os.environ,'PYTHONPATH':str(PROJECT)}
        log=open(p/'artifacts/manager.log','a')
        proc=subprocess.Popen([sys.executable,'-m','feedverse.cli','--root',str(self.root),'_job',jid],cwd=PROJECT,env=env,stdout=log,stderr=log,start_new_session=True); log.close()
        with self.db() as db: db.execute('UPDATE jobs SET pid=? WHERE id=? AND pid IS NULL',(proc.pid,jid))
        threading.Thread(target=proc.wait,daemon=True).start()
        return self.get_job_status(jid)
    def run_job(self,jid):
        with self.db() as db:
            job=db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
            changed=db.execute("UPDATE jobs SET state='running',pid=? WHERE id=? AND state='queued'",(os.getpid(),jid)).rowcount
        if not changed: return
        p=self.path(job['variant']); stable=p/'artifacts'; a=p/'attempts'/jid; a.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(stable/'config.json',a/'config.json')
        try:
            if self.identity(job['variant'])!=json.loads(job['identity']): raise ValueError('Job identity mismatch')
            # Every launch revalidates isolation, including resumed jobs.
            probe(self.root/'isolation')
            env={**os.environ,'TMPDIR':str(a/'tmp'),'KMP_USE_SHM':'0','PYTHONDONTWRITEBYTECODE':'1'}
            with open(a/'train.log','w') as f:
                child=subprocess.Popen(command(p/'source/model.py',self.public,a,'train',self.public/'train.json'),cwd=p/'source',env=env,stdout=f,stderr=f)
                try: code=child.wait(timeout=1800)
                except subprocess.TimeoutExpired:
                    child.kill(); child.wait(); raise TimeoutError('Training exceeded 30 minutes')
            if code: raise RuntimeError('Training exit '+str(code)+'; see train.log')
            if self.identity(job['variant'])!=json.loads(job['identity']): raise ValueError('Identity changed during training')
            if sha(a/'config.json')!=sha(stable/'config.json'): raise ValueError('Attempt training config changed')
            receipt={'checkpoint_sha256':sha(a/'checkpoint.pt'),**json.loads(job['identity'])}
            dump(a/'checkpoint-identity.json',receipt)
            with self.db() as db:
                if db.execute('SELECT state FROM jobs WHERE id=?',(jid,)).fetchone()['state']!='running': raise ValueError('Attempt no longer active; artifacts not promoted')
                for filename in ['checkpoint.pt','train.log','checkpoint-identity.json']:
                    shutil.copyfile(a/filename,stable/filename)
            state='completed'; error=None
        except Exception as exc: state='failed'; error=type(exc).__name__+': '+str(exc)
        with self.db() as db: db.execute("UPDATE jobs SET state=?,finished=?,error=? WHERE id=? AND state='running'",(state,time.time(),error,jid))
    def get_job_status(self,job_id):
        with self.db() as db:
            row=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
        if not row: raise ValueError('Unknown job')
        r=dict(row); r['identity']=json.loads(r['identity'])
        if r['state'] in ['queued','running'] and r['pid']:
            try: os.kill(r['pid'],0)
            except ProcessLookupError:
                with self.db() as db: db.execute("UPDATE jobs SET state='interrupted',finished=?,error='Manager process lost' WHERE id=? AND state IN ('queued','running')",(time.time(),job_id))
                r['state']='interrupted'; r['error']='Manager process lost'
        log=self.path(r['variant'])/'attempts'/job_id/'train.log'
        if not log.exists(): log=self.path(r['variant'])/'artifacts/train.log'
        r['progress']=log.read_text()[-4000:] if log.exists() else ''
        return r
    def cancel(self,job_id):
        r=self.get_job_status(job_id)
        if r['state'] in ['queued','running']:
            with self.db() as db: db.execute("UPDATE jobs SET state='cancelled',finished=? WHERE id=?",(time.time(),job_id))
            if r['pid']:
                try: os.killpg(r['pid'],signal.SIGTERM)
                except ProcessLookupError: pass
        return self.get_job_status(job_id)
    def evaluate_variant(self,variant,split='validation'):
        try:
            result=self._evaluate_variant(variant,split)
            failure=self.path(variant)/(split+'-failure.json')
            if failure.exists(): failure.unlink()
            return result
        except Exception as exc:
            if split in ['validation','heldout'] and self.path(variant).exists():
                dump(self.path(variant)/(split+'-failure.json'),{'variant':variant,'split':split,'time':time.time(),'error':type(exc).__name__+': '+str(exc)})
            raise
    def _evaluate_variant(self,variant,split='validation'):
        if split not in ['validation','heldout']: raise ValueError('Invalid split')
        if self.exploration and split!='validation': raise ValueError('Web explorations are validation-only')
        if self.exploration and variant=='baseline': return json.loads((self.path('baseline')/'validation-evaluation.json').read_text())
        if split=='heldout':
            selection=json.loads((self.root/'selection.json').read_text())
            if variant not in ['baseline',selection['selected']]: raise ValueError('Only frozen baseline/selected model may use heldout')
        p=self.path(variant); a=p/'artifacts'; ident=self.identity(variant); ci=json.loads((a/'checkpoint-identity.json').read_text())
        if any(ci.get(k)!=v for k,v in ident.items()) or ci['checkpoint_sha256']!=sha(a/'checkpoint.pt'): raise ValueError('Checkpoint identity mismatch')
        rows=json.loads((self.frozen/(split+'.json')).read_text())
        # Keep labels in this trusted process only. Score child sees a stripped per-call file.
        score_dir=p/('score-'+split); score_dir.mkdir(exist_ok=True)
        for f in ['checkpoint.pt','config.json']: shutil.copyfile(a/f,score_dir/f)
        dump(score_dir/'input.json',[{k:v for k,v in r.items() if k!='positive'} for r in rows])
        env={**os.environ,'TMPDIR':str(score_dir/'tmp'),'KMP_USE_SHM':'0','PYTHONDONTWRITEBYTECODE':'1'}
        with open(score_dir/'score.log','w') as log:
            result=subprocess.run(command(p/'source/model.py',self.public,score_dir,'score',score_dir/'input.json'),cwd=p/'source',env=env,stdout=log,stderr=log,timeout=300)
        if result.returncode: raise RuntimeError('Scoring failed; '+(score_dir/'score.log').read_text()[-2000:])
        scores=json.loads((score_dir/'scores.json').read_text()); report={'variant':variant,'split':split,'identity':ci,'scores_sha256':sha(score_dir/'scores.json'),'metrics':metrics(rows,scores,json.loads((self.public/'seen.json').read_text()))}
        dump(p/(split+'-evaluation.json'),report); return report
    def inspect_run(self,variant):
        p=self.path(variant)
        report=json.loads((p/'validation-evaluation.json').read_text()) if (p/'validation-evaluation.json').exists() else None
        with self.db() as db: jobs=[dict(r) for r in db.execute('SELECT id,state,error,created,finished FROM jobs WHERE variant=? ORDER BY created',(variant,))]
        return {'variant':variant,'identity':self.identity(variant),'validation':report,'jobs':jobs}
    def compare_runs(self,variants):
        from collections import Counter
        if not variants or len(variants)>4: raise ValueError('Compare one to four variants')
        rows=json.loads((self.public/'validation-input.json').read_text()); reference=variants[0]
        def orders(v):
            scores=json.loads((self.path(v)/'score-validation/scores.json').read_text())
            if len(scores)!=len(rows): raise ValueError('Score count mismatch')
            return [[r['candidates'][i] for i in sorted(range(len(s)),key=lambda i:(-s[i],i))] for r,s in zip(rows,scores)]
        base=orders(reference); exposure0=Counter(n for order in base for n in order[:10]); results=[]
        for v in variants:
            ordered=orders(v); exposure=Counter(n for order in ordered for n in order[:10])
            delta=sorted([{'article':n,'reference_exposure':exposure0[n],'variant_exposure':exposure[n],'delta':exposure[n]-exposure0[n]} for n in set(exposure)|set(exposure0)],key=lambda x:(-x['delta'],x['article']))
            cases=[{'case_id':r['id'],'reference_top10':a[:10],'variant_top10':z[:10],'top10_jaccard':len(set(a[:10])&set(z[:10]))/len(set(a[:10])|set(z[:10]))} for r,a,z in zip(rows,base,ordered)]
            detail={'reference':reference,'variant':v,'article_exposure':delta,'cases':cases}
            target=self.path(v)/'comparison.json'; dump(target,detail)
            results.append({'variant':v,'report':self.inspect_run(v),'diff_from_baseline':self.diff(v),'ranking_comparison':{'reference':reference,'mean_top10_jaccard':sum(c['top10_jaccard'] for c in cases)/len(cases),'changed_top10_cases':sum(c['reference_top10']!=c['variant_top10'] for c in cases),'examples':cases[:5]},'exposure_comparison':{'largest_gains':delta[:10],'largest_losses':list(reversed(delta[-10:])),'complete_detail_sha256':sha(target)}})
        return results
    def diff(self,variant):
        import difflib
        return ''.join(difflib.unified_diff(self.read_source('baseline').splitlines(True),self.read_source(variant).splitlines(True),fromfile='baseline',tofile=variant))
    def recommend_case(self,variant,index=0):
        rows=json.loads((self.public/'validation-input.json').read_text())
        if not 0<=index<len(rows): raise ValueError('Invalid case index')
        scores=json.loads((self.path(variant)/'score-validation/scores.json').read_text()); r=rows[index]; order=sorted(range(len(r['candidates'])),key=lambda i:(-scores[index][i],i)); news=json.loads((self.public/'articles.json').read_text())
        return {'history':[{'id':n,**news[n]} for n in r['history']],'top10':[{'id':r['candidates'][i],'score':scores[index][i],**news[r['candidates'][i]]} for i in order[:10]]}
    def select(self):
        if (self.root/'selection.json').exists(): return json.loads((self.root/'selection.json').read_text())
        with self.db() as db:
            if db.execute("SELECT 1 FROM jobs WHERE state IN ('queued','running')").fetchone(): raise ValueError('Training still active')
            for row in db.execute("SELECT variant FROM jobs WHERE state='completed'"):
                if not (self.path(row['variant'])/'validation-evaluation.json').exists(): raise ValueError('Completed candidate lacks validation')
        reports=[]
        for p in sorted(self.variants.iterdir()):
            f=p/'validation-evaluation.json'
            if f.exists():
                r=json.loads(f.read_text()); identity=self.identity(p.name)
                if any(r['identity'].get(k)!=v for k,v in identity.items()): raise ValueError('Report identity changed')
                if sha(p/'artifacts/checkpoint.pt')!=r['identity']['checkpoint_sha256']: raise ValueError('Checkpoint changed')
                if sha(p/'score-validation/scores.json')!=r['scores_sha256']: raise ValueError('Scores changed')
                reports.append(r)
        base=next(r for r in reports if r['variant']=='baseline'); best=base
        for r in reports:
            x=r['metrics']['cold']['NDCG@10']; b=best['metrics']['cold']['NDCG@10']
            if x is not None and b is not None and x>b: best=r
        result={'selected':best['variant'],'criterion':'validation cold NDCG@10 strictly exceeds baseline; no overall-drop constraint','reports_sha256':{r['variant']:sha(self.path(r['variant'])/'validation-evaluation.json') for r in reports},'selected_identity':best['identity'],'time':time.time()}
        dump(self.root/'selection.json',result); return result
