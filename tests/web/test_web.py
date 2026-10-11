import asyncio,json,os,tempfile,time,unittest,sqlite3
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from feedverse.web_api import create_app
from feedverse.web_store import Store,HISTORY_ID,redact
from feedverse.backend import Backend,PROJECT
from feedverse.mcp import dispatch
from feedverse.data import dump,sha

class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'web',PROJECT/'local/core');self.launches=[]
        def fake_launch(store,eid):
            self.launches.append(eid);store.update(eid,status='running',pid=os.getpid());return store.get(eid)
        self.app=create_app(self.store,fake_launch);self.client=TestClient(self.app)
        self.body={'title':'fixture','instruction':'Content modeling','candidate_limit':1,'request_key':'request-key-0001'}
    def tearDown(self):self.client.close();self.temp.cleanup()
    def test_idempotence_and_single_active(self):
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda _:self.client.post('/api/explorations',json=self.body).json(),range(4)))
        self.assertEqual(len({r['id'] for r in results}),1);self.assertEqual(len(self.launches),1)
        other=self.client.post('/api/explorations',json={**self.body,'request_key':'second-request-0002'}).json();self.assertEqual(other['id'],results[0]['id']);self.assertFalse(other['created'])
    def test_cancel_resume_and_completed_no_restart(self):
        eid=self.client.post('/api/explorations',json=self.body).json()['id']
        self.assertEqual(self.client.post(f'/api/explorations/{eid}/cancel').json()['status'],'cancelling')
        self.store.update(eid,status='cancelled',pid=None)
        self.assertEqual(self.client.post(f'/api/explorations/{eid}/resume').json()['status'],'running');self.assertEqual(len(self.launches),2)
        self.store.update(eid,status='completed',pid=None)
        self.assertEqual(self.client.post(f'/api/explorations/{eid}/resume').json()['status'],'completed');self.assertEqual(len(self.launches),2)
        self.assertFalse(self.client.post('/api/explorations',json=self.body).json()['created'])
    def test_process_loss_is_interrupted(self):
        eid=self.client.post('/api/explorations',json=self.body).json()['id'];self.store.update(eid,pid=99999999,status='running');self.store.reconcile()
        self.assertEqual(self.store.get(eid)['status'],'interrupted');self.client.post(f'/api/explorations/{eid}/resume');self.assertEqual(len(self.launches),2)
    def test_invalid_configuration_and_origin(self):
        for count in [0,4]:self.assertEqual(self.client.post('/api/explorations',json={**self.body,'candidate_limit':count}).status_code,422)
        for extra in [{'root':'/tmp/other'},{'command':'whoami'},{'epochs':1}]:self.assertEqual(self.client.post('/api/explorations',json={**self.body,**extra}).status_code,422)
        self.assertEqual(self.client.post('/api/explorations',json=self.body,headers={'Origin':'https://external.example'}).status_code,403)
        self.assertEqual(self.client.post('/api/experiments/'+HISTORY_ID+'/heldout').status_code,405)
    def test_real_results_cases_and_distribution(self):
        before=sha(PROJECT/'local/core/variants/baseline/validation-evaluation.json')
        r=self.client.get('/api/experiments/'+HISTORY_ID).json();stored=json.loads((PROJECT/'local/core/variants/attention_content/validation-evaluation.json').read_text())
        actual=next(m for m in r['models'] if m['id']=='attention_content');self.assertEqual(actual['metrics'],stored['metrics']);self.assertEqual(r['usage']['tokens']['total_tokens'],489271)
        cases=self.client.get(f'/api/experiments/{HISTORY_ID}/cases').json();self.assertEqual(cases['total'],1000);self.assertEqual(cases['items'][0]['index'],0)
        cold=self.client.get(f'/api/experiments/{HISTORY_ID}/cases?cold=true').json();self.assertEqual(cold['total'],685)
        case=self.client.get(f'/api/experiments/{HISTORY_ID}/cases/0?variant=attention_content').json();raw=json.loads((PROJECT/'local/core/frozen/validation.json').read_text())[0]
        self.assertEqual(case['positive']['id'],raw['positive']);scores=json.loads((PROJECT/'local/core/variants/attention_content/score-validation/scores.json').read_text())[0]
        expected=[raw['candidates'][i] for i in sorted(range(len(scores)),key=lambda i:(-scores[i],i))]
        self.assertEqual([a['id'] for a in case['candidate']],expected)
        dist=self.client.get(f'/api/experiments/{HISTORY_ID}/distribution?variant=attention_content').json();self.assertEqual(sum(a['candidate'] for a in dist['items']),10000);self.assertEqual(sum(a['baseline'] for a in dist['items']),10000)
        self.assertEqual(before,sha(PROJECT/'local/core/variants/baseline/validation-evaluation.json'))
    def test_event_dedup_redaction_and_sse_cursor(self):
        eid=self.client.post('/api/explorations',json=self.body).json()['id'];runtime=self.store.path(eid)/'runtime';runtime.mkdir(parents=True)
        rows=[{'time':1,'event':'upstream','status':429},{'time':2,'event':'upstream','status':401}]
        (runtime/'bridge-audit.jsonl').write_text('\n'.join(map(json.dumps,rows))+'\n');self.store.ingest(eid);self.store.ingest(eid)
        events=self.store.events(eid);self.assertEqual(len(events),3);self.assertEqual(sum(e['kind']=='error' for e in events),2)
        endpoint=next(r.endpoint for r in self.app.routes if r.path=='/api/experiments/{eid}/events')
        class Request:
            headers={'last-event-id':str(events[0]['seq'])}
            async def is_disconnected(self):return False
        async def check():
            response=await endpoint(eid,Request(),0);data=await response.body_iterator.__anext__();await response.body_iterator.aclose();return data
        first=asyncio.run(check());self.assertIn('id: '+str(events[1]['seq']),first)
        value=redact({'apiKey':'sensitive','Authorization':'Bearer abc','usage':{'tokens':{'total_tokens':12}},'text':'Bearer abc /Users/river/private/file'})
        self.assertNotIn('sensitive',json.dumps(value));self.assertNotIn('Bearer abc',json.dumps(value));self.assertEqual(value['usage']['tokens']['total_tokens'],12)
    def test_new_exploration_feedback_and_candidate_limits(self):
        # No training: this fixture tests the same MCP boundary used by real AGH.
        for limit in [1,2,3]:
            root=Path(self.temp.name)/f'core{limit}';root.mkdir();dump(root/'exploration-spec.json',{'candidate_limit':limit,'validation_only':True,'instruction':'x'})
            b=Backend(root);b.create_variant('baseline',None)
            for i in range(limit):b.create_variant('candidate_'+str(i+1),description='内容表示')
            with self.assertRaises(ValueError):b.create_variant('candidate_'+str(limit+1))
            with self.assertRaises(ValueError):b.train_variant('baseline')
            with self.assertRaises(ValueError):b.evaluate_variant('candidate_1','heldout')
            r=dispatch(b,{'id':1,'method':'tools/call','params':{'name':'evaluate_variant','arguments':{'variant':'candidate_1','split':'heldout'}}});self.assertTrue(r['result']['isError'])
    def test_incomplete_usage_stays_missing(self):
        eid=self.client.post('/api/explorations',json=self.body).json()['id'];runtime=self.store.path(eid)/'runtime';runtime.mkdir(parents=True)
        rows=[{'time':1,'event':'request','request_id':'a'}, {'time':2,'event':'response.failed','request_id':'a','status':'failed','usage':None}, {'time':3,'event':'request','request_id':'b'}, {'time':4,'event':'response.completed','request_id':'b','status':'completed','usage':{'input_tokens':10,'output_tokens':1,'total_tokens':11}}, {'time':5,'event':'request','request_id':'c'}]
        (runtime/'bridge-audit.jsonl').write_text('\n'.join(map(json.dumps,rows))+'\n');result=self.store.snapshot(eid)
        self.assertEqual(result['usage']['missing_usage_requests'],2);self.assertEqual(result['usage']['tokens']['total_tokens'],11);self.assertEqual(result['usage']['confirmed_responses'],1)
        self.assertIsNone(result['heldout']);self.assertTrue(any(e['kind']=='error' for e in self.store.events(eid)))
    def test_source_and_export_are_allowlisted(self):
        source=self.client.get(f'/api/experiments/{HISTORY_ID}/models/attention_content/source').json();self.assertEqual(source['sha256'],sha(PROJECT/'models/attention_content.py'));self.assertIn('self.temperature',source['diff'])
        self.assertEqual(self.client.get(f'/api/experiments/{HISTORY_ID}/models/no-such/source').status_code,404)
        export=self.client.get(f'/api/experiments/{HISTORY_ID}/export').json();self.assertEqual(export['snapshot']['usage']['tokens']['total_tokens'],489271);self.assertNotIn('apiKey',json.dumps(export))

class BridgeHttpTests(unittest.TestCase):
    """Exercise the actual bridge HTTP handler with controlled upstream receipts, no TRAPI calls."""
    def handler(self,root,status):
        import ast,types
        from http.server import BaseHTTPRequestHandler
        import hmac,secrets
        script=PROJECT/'scripts/trapi_bridge.py';tree=ast.parse(script.read_text());nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in ['audit','Handler']]
        class Credential:
            calls=0
            def get_token(self,*args):self.calls+=1;return types.SimpleNamespace(token='fixture-token')
        cred=Credential()
        class Upstream:
            status_code=status;headers={'Content-Type':'application/json','Retry-After':'1'}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def iter_content(self,**kwargs):yield json.dumps({'error':{'message':'controlled upstream error'}}).encode()
        namespace={'BaseHTTPRequestHandler':BaseHTTPRequestHandler,'ROOT':root,'C':{'instance':'fixture','model':'gpt-6-astra','deployment':'gpt-6-astra_2026-09-03','requestTimeoutSeconds':1},'KEY':'fixture-key','hmac':hmac,'time':time,'uuid':__import__('uuid'),'json':json,'credential':cred,'URL':'http://fixture','auth_failed':False,'requests':types.SimpleNamespace(post=lambda *a,**k:Upstream())}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),str(script),'exec'),namespace)
        return namespace,cred
    def test_401_stops_queue_and_429_preserves_retry_after(self):
        import requests,threading
        from http.server import ThreadingHTTPServer
        for status in [401,429]:
            with tempfile.TemporaryDirectory() as d:
                namespace,cred=self.handler(Path(d),status);server=ThreadingHTTPServer(('127.0.0.1',0),namespace['Handler']);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                try:
                    url=f'http://127.0.0.1:{server.server_port}/v1/responses';headers={'Authorization':'Bearer fixture-key'};body={'model':'gpt-6-astra','stream':False}
                    first=requests.post(url,headers=headers,json=body,timeout=2);self.assertEqual(first.status_code,status);self.assertEqual(first.headers['Retry-After'],'1')
                    second=requests.post(url,headers=headers,json=body,timeout=2);self.assertEqual(second.status_code,status)
                    self.assertEqual(cred.calls,1 if status==401 else 2);self.assertEqual(namespace['auth_failed'],status==401)
                    audit=(Path(d)/'bridge-audit.jsonl').read_text();self.assertNotIn('fixture-token',audit);self.assertIn('"status": '+str(status),audit)
                finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
