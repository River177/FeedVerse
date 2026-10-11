"""Durable web exploration registry and read-only experiment projections."""
import json, math, os, re, sqlite3, time, uuid
from contextlib import contextmanager, closing
from collections import Counter
from functools import lru_cache
from pathlib import Path
from .backend import PROJECT
from .data import sha

ACTIVE=('preparing','running','cancelling')
TERMINAL=('completed','cancelled','failed','interrupted')
HISTORY_ID='verified-20261010'

def read_json(p,default=None):
    return json.loads(Path(p).read_text()) if Path(p).exists() else default

@lru_cache(maxsize=12)
def cached_json(path,mtime): return json.loads(Path(path).read_text())
def load(p): return cached_json(str(p),Path(p).stat().st_mtime_ns)

def redact(value):
    if isinstance(value,dict): return {k:('[redacted]' if re.search('token|authorization|api.?key|secret|credential',k,re.I) and k not in ['tokens','input_tokens','output_tokens','total_tokens','cached_tokens','reasoning_tokens','input_tokens_details','output_tokens_details','cache_write_tokens'] else redact(v)) for k,v in value.items()}
    if isinstance(value,list): return [redact(x) for x in value]
    if isinstance(value,str):
        value=re.sub(r'Bearer\s+[\w.\-]+','Bearer [redacted]',value)
        value=re.sub(r'/Users/[^\s"\n]+','[local path]',value)
        return value[:24000]
    return value

class Store:
    def __init__(self,root=None,history=None):
        self.root=Path(root or os.getenv('FEEDVERSE_WEB_ROOT',PROJECT/'local/web')).resolve()
        self.history=Path(history or os.getenv('FEEDVERSE_HISTORY_ROOT',PROJECT/'local/core')).resolve()
        self.root.mkdir(parents=True,exist_ok=True)
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS explorations (id TEXT PRIMARY KEY, request_key TEXT UNIQUE, title TEXT, instruction TEXT, candidate_limit INTEGER, status TEXT, pid INTEGER, created REAL, updated REAL, error TEXT)')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS one_active ON explorations ((1)) WHERE status IN (\'preparing\',\'running\',\'cancelling\')')
            db.execute('CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, experiment TEXT, source TEXT, source_key TEXT, time REAL, kind TEXT, title TEXT, payload TEXT, UNIQUE(experiment,source,source_key))')
    @contextmanager
    def db(self):
        c=sqlite3.connect(self.root/'web.sqlite',timeout=30);c.row_factory=sqlite3.Row
        try:
            with c: yield c
        finally:c.close()
    def path(self,eid):
        if not re.fullmatch('exp_[0-9a-f]{16}',eid): raise ValueError('Unknown experiment')
        return self.root/'explorations'/eid
    def get(self,eid):
        with self.db() as db: r=db.execute('SELECT * FROM explorations WHERE id=?',(eid,)).fetchone()
        if r is None: raise ValueError('Unknown experiment')
        return dict(r)
    def create(self,title,instruction,limit,key):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            r=db.execute('SELECT * FROM explorations WHERE request_key=?',(key,)).fetchone()
            if r:return dict(r),False
            r=db.execute("SELECT * FROM explorations WHERE status IN ('preparing','running','cancelling')").fetchone()
            if r:return dict(r),False
            eid='exp_'+uuid.uuid4().hex[:16];now=time.time()
            db.execute('INSERT INTO explorations VALUES (?,?,?,?,?,?,?,?,?,?)',(eid,key,title,instruction,limit,'preparing',None,now,now,None))
        self.event(eid,'lifecycle','created','lifecycle','创建真实探索',{'candidate_limit':limit,'instruction':instruction})
        return self.get(eid),True
    def update(self,eid,**fields):
        allowed={'status','pid','error'}
        if set(fields)-allowed:raise ValueError('Invalid state fields')
        fields['updated']=time.time()
        with self.db() as db:db.execute('UPDATE explorations SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',(*fields.values(),eid))
    def event(self,eid,source,key,kind,title,payload,when=None):
        with self.db() as db:db.execute('INSERT OR IGNORE INTO events (experiment,source,source_key,time,kind,title,payload) VALUES (?,?,?,?,?,?,?)',(eid,source,key,when or time.time(),kind,title,json.dumps(redact(payload),ensure_ascii=False)))
    def events(self,eid,after=0,limit=300):
        with self.db() as db:rows=db.execute('SELECT * FROM events WHERE experiment=? AND seq>? ORDER BY seq LIMIT ?',(eid,after,limit)).fetchall()
        return [{**dict(r),'payload':json.loads(r['payload'])} for r in rows]
    def event_max(self,eid):
        with self.db() as db:return db.execute('SELECT COALESCE(MAX(seq),0) FROM events WHERE experiment=?',(eid,)).fetchone()[0]
    def ingest(self,eid):
        pending=[]
        def add(eid,source,key,kind,title,payload,when=None):pending.append((eid,source,key,when or time.time(),kind,title,json.dumps(redact(payload),ensure_ascii=False)))
        runtime=self.history.parent/'agh-runtime' if eid==HISTORY_ID else self.path(eid)/'runtime'
        core=self.history if eid==HISTORY_ID else self.path(eid)/'core'
        for source,file in [('sdk',runtime/'sdk-events.jsonl'),('mcp',core/'mcp-events.jsonl'),('bridge',runtime/'bridge-audit.jsonl')]:
            if not file.exists():continue
            # Saved source keys make reads idempotent and SSE replay independent of connection lifetime.
            with self.db() as db:known=db.execute('SELECT COALESCE(MAX(CAST(source_key AS INTEGER)),-1) FROM events WHERE experiment=? AND source=?',(eid,source)).fetchone()[0]
            for i,line in enumerate(file.read_text().splitlines()):
                if i<=known:continue
                try:r=json.loads(line)
                except ValueError:continue
                kind='tool';title=source;payload=r;when=r.get('time',time.time())
                if source=='sdk':
                    if 'permission' in r:continue
                    u=r.get('params',{}).get('update',{})
                    t=u.get('sessionUpdate')
                    if t in ['tool_call','tool_call_update']:
                        payload=u;title=u.get('title',u.get('toolCallId','工具结果'))
                    elif t=='agent_message_chunk':kind='message';title='AGH';payload={'text':u.get('content',{}).get('text','')}
                    elif r.get('errorType'):kind='error';title=r['errorType']
                    elif 'operation' in r and r['operation'].get('state')=='failed':kind='error';title='MCP 配置失败'
                    else:continue
                elif source=='mcp':
                    kind='error' if 'error' in r else 'tool';title=r.get('tool',r.get('request',{}).get('params',{}).get('name','工具失败'))
                else:
                    title=r['event'];bad=(isinstance(r.get('status'),int) and r['status']>=400) or r['event'] in ['bridge_error','response.failed','response.incomplete'];kind='error' if bad else 'usage' if r.get('usage') is not None and r['event'] in ['response.completed','response_json'] else 'request'
                add(eid,source,str(i),kind,title,payload,when)
        if (core/'state.sqlite').exists():
            with closing(sqlite3.connect(f'file:{core}/state.sqlite?mode=ro',uri=True)) as c:jobs=c.execute('SELECT id,variant,state FROM jobs').fetchall()
            with self.db() as db:known_training={r[0] for r in db.execute("SELECT source_key FROM events WHERE experiment=? AND source='training'",(eid,))}
            for jid,variant,state in jobs:
                file=core/'variants'/variant/'attempts'/jid/'train.log'
                if not file.exists():file=core/'variants'/variant/'artifacts/train.log'
                if file.exists():
                    for i,line in enumerate(file.read_text().splitlines()):
                        if jid+':'+str(i) in known_training:continue
                        if line.startswith('{'):
                            try:p=json.loads(line)
                            except ValueError:continue
                            add(eid,'training',jid+':'+str(i),'training',variant+' · epoch '+str(p.get('epoch')),{'job_id':jid,'variant':variant,'timestamp_source':'log_mtime',**p},file.stat().st_mtime)
        if pending:
            pending.sort(key=lambda x:x[3])
            with self.db() as db:db.executemany('INSERT OR IGNORE INTO events (experiment,source,source_key,time,kind,title,payload) VALUES (?,?,?,?,?,?,?)',pending)
    def reconcile(self):
        with self.db() as db:rows=[dict(r) for r in db.execute("SELECT * FROM explorations WHERE status IN ('preparing','running','cancelling')")]
        for r in rows:
            if not r['pid'] and time.time()-r['created']<15:continue
            try:
                if not r['pid']:raise ProcessLookupError
                os.kill(r['pid'],0)
            except ProcessLookupError:
                self.update(r['id'],status='interrupted',pid=None,error='探索进程中断；请按原身份恢复')
                self.event(r['id'],'lifecycle','interrupted:'+str(r['updated']),'error','探索中断',{'recoverable':True})
    def listing(self):
        self.reconcile()
        with self.db() as db:rows=[dict(r) for r in db.execute('SELECT * FROM explorations ORDER BY created DESC')]
        historical={'id':HISTORY_ID,'title':'MIND 冷启动 · 已核验实验','status':'completed','candidate_limit':3,'created':read_json(self.history/'selection.json',{}).get('time',0),'historical':True}
        return [historical,*[{**r,'historical':False} for r in rows]]
    def view(self,eid):
        return ExperimentView(self.history if eid==HISTORY_ID else self.path(eid)/'core')
    def snapshot(self,eid):
        info=self.listing()[0] if eid==HISTORY_ID else {**self.get(eid),'historical':False}
        view=self.view(eid);self.ingest(eid)
        usage=Counter();confirmed=0;requests=0;missing=0;request_ids=set();usage_by_request={}
        runtime=self.history.parent/'agh-runtime' if eid==HISTORY_ID else self.path(eid)/'runtime'
        f=runtime/'bridge-audit.jsonl'
        if f.exists():
            for line in f.read_text().splitlines():
                try:r=json.loads(line)
                except ValueError:continue
                if r['event']=='request':requests+=1;request_ids.add(r['request_id'])
                if r['event'] in ['response.completed','response.failed','response.incomplete','response_json'] and r.get('usage'):
                    usage_by_request[r['request_id']]=r['usage']
                    if r['event']=='response.completed' or r.get('status')=='completed':confirmed+=1
            for value in usage_by_request.values():
                for k in ['input_tokens','output_tokens','total_tokens']:usage[k]+=value.get(k,0)
            missing=len(request_ids-set(usage_by_request))
        receipt=read_json(runtime/'exploration.json',{})
        if info.get('error'):info['error']=redact(info['error'])
        return {**info,'models':view.models(),'selection':read_json(view.root/'selection.json'),'counts':{'train':20000,'validation':1000},'protocol':'MIND 冷启动 · seed 42 · CPU · batch 128 · 5 epochs','session_id':receipt.get('sessionId'),'event_seq':self.event_max(eid),'usage':{'requests':requests,'confirmed_responses':confirmed,'missing_usage_requests':missing,'tokens':dict(usage) if usage_by_request else None,'estimated_credits':receipt.get('credits'),'cost':None},'heldout':view.heldout() if eid==HISTORY_ID else None}

class ExperimentView:
    def __init__(self,root):self.root=Path(root)
    def models(self):
        results=[];variants=self.root/'variants'
        if not variants.exists():return []
        for p in sorted(variants.iterdir(),key=lambda x:(x.name!='baseline',x.name)):
            r=read_json(p/'validation-evaluation.json');failure=read_json(p/'validation-failure.json');meta=read_json(p/'variant.json',{})
            log=p/'artifacts/train.log';epochs=[];jobs=[]
            if (self.root/'state.sqlite').exists():
                with closing(sqlite3.connect(f'file:{self.root}/state.sqlite?mode=ro',uri=True)) as c:
                    c.row_factory=sqlite3.Row;jobs=[dict(x) for x in c.execute('SELECT id,state,created,finished,error FROM jobs WHERE variant=? ORDER BY created',(p.name,))]
            if jobs:
                attempt=p/'attempts'/jobs[-1]['id']/'train.log'
                if attempt.exists():log=attempt
            if log.exists():
                for line in log.read_text().splitlines():
                    if line.startswith('{'):
                        try:epochs.append(json.loads(line))
                        except ValueError:pass
            status='evaluated' if r else 'evaluation_failed' if failure else jobs[-1]['state'] if jobs else 'created'
            results.append({'id':p.name,'status':status,'reused':bool(meta.get('imported')),'metrics':r['metrics'] if r else None,'identity':r['identity'] if r else read_json(p/'artifacts/identity.json'),'jobs':jobs,'epochs':epochs,'failure':redact(failure),'description':meta.get('description')})
        return results
    def source(self,variant):
        if not re.fullmatch('[a-z][a-z0-9_-]{0,47}',variant):raise ValueError('Invalid model')
        p=self.root/'variants'/variant/'source/model.py'
        if not p.exists():raise ValueError('Unknown model')
        import difflib
        baseline=(self.root/'variants/baseline/source/model.py').read_text();s=p.read_text()
        return {'source':s,'sha256':sha(p),'diff':''.join(difflib.unified_diff(baseline.splitlines(True),s.splitlines(True),fromfile='baseline',tofile=variant))}
    def data(self):return load(self.root/'frozen/validation.json'),load(self.root/'public/articles.json'),set(load(self.root/'public/seen.json'))
    def scores(self,variant):
        if not re.fullmatch('[a-z][a-z0-9_-]{0,47}',variant):raise ValueError('Invalid model')
        p=self.root/'variants'/variant/'score-validation/scores.json';r=read_json(self.root/'variants'/variant/'validation-evaluation.json')
        if r is None or not p.exists():raise ValueError('Model has no validated ranking')
        return load(p)
    def cases(self,query='',cold=False,page=0,size=20):
        rows,news,seen=self.data();hits=[]
        for i,r in enumerate(rows):
            if cold and r['positive'] in seen:continue
            if query.lower() not in (r['id']+' '+news[r['positive']]['title']).lower():continue
            hits.append({'index':i,'id':r['id'],'cold':r['positive'] not in seen,'title':news[r['positive']]['title'],'candidate_count':len(r['candidates'])})
        return {'total':len(hits),'items':hits[page*size:(page+1)*size]}
    def case(self,index,variant):
        rows,news,seen=self.data()
        if not 0<=index<len(rows):raise ValueError('Unknown case')
        r=rows[index]
        def article(n):return {'id':n,**news[n],'cold':n not in seen}
        def ranking(model):
            s=self.scores(model)[index];order=sorted(range(len(s)),key=lambda i:(-s[i],i))
            return [{**article(r['candidates'][i]),'rank':k+1,'score':s[i],'clicked':r['candidates'][i]==r['positive']} for k,i in enumerate(order)]
        return {'id':r['id'],'index':index,'positive':article(r['positive']),'history':[article(n) for n in r['history']],'baseline':ranking('baseline'),'candidate':ranking(variant)}
    def distribution(self,variant):
        rows,news,seen=self.data();catalogue={n for r in rows for n in r['candidates']}
        def exposures(v):
            ss=self.scores(v);c=Counter()
            for r,s in zip(rows,ss):c.update(r['candidates'][i] for i in sorted(range(len(s)),key=lambda i:(-s[i],i))[:10])
            return c
        base=exposures('baseline');other=exposures(variant)
        items=[{'id':n,**news[n],'cold':n not in seen,'baseline':base[n],'candidate':other[n],'delta':other[n]-base[n]} for n in sorted(catalogue)]
        return {'items':items,'case_count':len(rows),'catalogue_count':len(catalogue),'definition':'固定验证候选集上的离线 Top10 入选次数'}
    def heldout(self):
        selection=read_json(self.root/'selection.json',{})
        return [read_json(self.root/'variants'/v/'heldout-evaluation.json') for v in dict.fromkeys(['baseline',selection.get('selected','baseline')]) if (self.root/'variants'/v/'heldout-evaluation.json').exists()]
