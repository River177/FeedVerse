"""MCP JSON-RPC service over stdio or loopback HTTP. No arbitrary paths or heldout tools."""
import json,sys,time
from http.server import BaseHTTPRequestHandler,HTTPServer
TOOLS={
'inspect_dataset':('Inspect permitted dataset statistics',{}),
'inspect_run':('Inspect training and validation receipts',{'variant':'string'}),
'create_variant':('Create independent source branch; maximum three candidates',{'name':'string','base':'string','description':'string'}),
'read_source':('Read model.py only',{'variant':'string'}),
'patch_source':('Replace editable candidate model.py with executable Python source',{'variant':'string','source':'string'}),
'train_variant':('Start real asynchronous five-epoch training; returns job ID',{'variant':'string'}),
'get_job_status':('Read job progress and terminal status',{'job_id':'string'}),
'evaluate_variant':('Reload completed model and evaluate fixed validation set',{'variant':'string'}),
'recommend_case':('Inspect permitted validation input and model rankings',{'variant':'string','index':'integer'}),
'compare_runs':('Compare validation metrics and code diffs',{'variants':'array'}),
}

def dispatch(backend,request):
    audit=backend.root/'mcp-events.jsonl'; method=request.get('method',''); params=request.get('params',{})
    try:
        if method=='initialize': result={'protocolVersion':params.get('protocolVersion','2024-11-05'),'capabilities':{'tools':{}},'serverInfo':{'name':'feedverse','version':'1.0.0'}}
        elif method=='ping': result={}
        elif method=='tools/list':
            result={'tools':[{'name':name,'description':desc,'inputSchema':{'type':'object','properties':{k:({'type':v,'items':{'type':'string'}} if v=='array' else {'type':v}) for k,v in fields.items()},'required':[k for k in fields if not (name=='create_variant' and k in ['base','description']) and not (name=='recommend_case' and k=='index')],'additionalProperties':False}} for name,(desc,fields) in TOOLS.items()]}
        elif method=='tools/call':
            name=params['name']; args=params.get('arguments',{})
            if name not in TOOLS: raise ValueError('Unknown tool')
            if set(args)-set(TOOLS[name][1]): raise ValueError('Unexpected tool arguments')
            value=getattr(backend,name)(**args)
            result={'content':[{'type':'text','text':json.dumps(value,ensure_ascii=False)}],'isError':False}
            with audit.open('a') as f: f.write(json.dumps({'time':time.time(),'tool':name,'arguments':args,'result':value},ensure_ascii=False)+'\n')
        elif method.startswith('notifications/'): return None
        else: raise ValueError('Unsupported method')
        return {'jsonrpc':'2.0','id':request.get('id'),'result':result}
    except Exception as e:
        message=type(e).__name__+': '+str(e)
        with audit.open('a') as f: f.write(json.dumps({'time':time.time(),'request':request,'error':message})+'\n')
        return {'jsonrpc':'2.0','id':request.get('id'),'result':{'content':[{'type':'text','text':message}],'isError':True}} if method=='tools/call' else {'jsonrpc':'2.0','id':request.get('id'),'error':{'code':-32603,'message':message}}

def serve(backend):
    for line in sys.stdin:
        try: request=json.loads(line); response=dispatch(backend,request)
        except ValueError: response={'jsonrpc':'2.0','id':None,'error':{'code':-32700,'message':'Invalid JSON'}}
        if response is not None: print(json.dumps(response,ensure_ascii=False),flush=True)

def serve_http(backend,port=18778):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            if self.path!='/mcp': self.send_error(404); return
            origin=self.headers.get('Origin')
            if origin and origin not in [f'http://127.0.0.1:{port}',f'http://localhost:{port}']: self.send_error(403); return
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=2*1024*1024: self.send_error(413); return
            try: request=json.loads(self.rfile.read(size)); response=dispatch(backend,request)
            except ValueError: self.send_error(400); return
            if response is None: self.send_response(202); self.end_headers(); return
            content=json.dumps(response,ensure_ascii=False).encode(); self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(content))); self.end_headers(); self.wfile.write(content)
        def do_GET(self): self.send_error(405)
        def do_DELETE(self): self.send_response(200); self.end_headers()
    HTTPServer(('127.0.0.1',port),Handler).serve_forever()
