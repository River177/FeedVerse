"""Parameterized loopback Responses bridge; secrets never appear in receipts."""
import hmac,json,os,secrets,time,uuid,argparse
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import requests
from azure.identity import AzureCliCredential
p=argparse.ArgumentParser(); p.add_argument('--root',required=True); p.add_argument('--config',required=True); args=p.parse_args()
ROOT=Path(args.root).resolve(); ROOT.mkdir(parents=True,exist_ok=True); C=json.loads(Path(args.config).read_text()); KEY_FILE=ROOT/'bridge.key'
if not KEY_FILE.exists():
    fd=os.open(KEY_FILE,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f: f.write(secrets.token_urlsafe(32))
KEY=KEY_FILE.read_text().strip(); credential=AzureCliCredential(); auth_failed=False
URL=f"https://trapi.research.microsoft.com/{C['instance']}/openai/responses?api-version={C['apiVersion']}"
def audit(**row):
    with (ROOT/'bridge-audit.jsonl').open('a') as f: f.write(json.dumps({'time':time.time(),**row})+'\n')
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def reply(self,status,value):
        data=json.dumps(value).encode(); self.send_response(status); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def authorized(self): return hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+KEY)
    def do_GET(self):
        if not self.authorized(): return self.reply(401,{'error':{'message':'Bridge authentication required'}})
        if self.path=='/v1/models': return self.reply(200,{'object':'list','data':[{'id':C['model'],'object':'model','owned_by':'trapi'}]})
        return self.reply(404,{'error':{'message':'Unknown route'}})
    def do_POST(self):
        global auth_failed
        if not self.authorized(): return self.reply(401,{'error':{'message':'Bridge authentication required'}})
        if auth_failed: return self.reply(401,{'error':{'message':'TRAPI authentication failed; queue stopped'}})
        if self.path!='/v1/responses': return self.reply(404,{'error':{'message':'Responses only'}})
        size=int(self.headers.get('Content-Length','0'))
        if not 0<size<=8*1024*1024: return self.reply(413,{'error':{'message':'Invalid request length'}})
        body=json.loads(self.rfile.read(size)); rid=uuid.uuid4().hex; started=time.monotonic(); sent=False
        if body.get('model') not in [C['model'],C['deployment']]: return self.reply(400,{'error':{'message':'Unexpected model'}})
        body['model']=C['deployment']; audit(event='request',request_id=rid,deployment=C['deployment'],streaming=bool(body.get('stream')))
        try:
            token=credential.get_token('api://trapi/.default').token
            with requests.post(URL,headers={'Authorization':'Bearer '+token},json=body,stream=True,timeout=(20,C['requestTimeoutSeconds'])) as upstream:
                if upstream.status_code in [401,403]: auth_failed=True
                audit(event='upstream',request_id=rid,status=upstream.status_code,upstream_request_id=upstream.headers.get('apim-request-id') or upstream.headers.get('x-request-id'))
                self.send_response(upstream.status_code)
                for header in ['Retry-After','retry-after-ms']:
                    if header in upstream.headers: self.send_header(header,upstream.headers[header])
                self.send_header('Content-Type',upstream.headers.get('Content-Type','application/json')); self.send_header('Connection','close'); self.end_headers(); sent=True
                pending=b''; complete=False; usage=None; response_id=None; nonstream=b''
                for chunk in upstream.iter_content(chunk_size=4096):
                    if not chunk: continue
                    self.wfile.write(chunk); self.wfile.flush()
                    if body.get('stream'):
                        pending+=chunk
                        while b'\n' in pending:
                            line,pending=pending.split(b'\n',1)
                            if line.startswith(b'data: '):
                                try: event=json.loads(line[6:])
                                except ValueError: continue
                                if event.get('type') in ['response.completed','response.failed','response.incomplete']:
                                    response=event.get('response',{}); usage=response.get('usage'); response_id=response.get('id'); complete=event['type']=='response.completed'
                                    audit(event=event['type'],request_id=rid,response_id=response_id,usage=usage,status=response.get('status'))
                    elif len(nonstream)<8*1024*1024: nonstream+=chunk
                if not body.get('stream'):
                    response=json.loads(nonstream); usage=response.get('usage'); response_id=response.get('id'); complete=response.get('status')=='completed'; audit(event='response_json',request_id=rid,response_id=response_id,usage=usage,status=response.get('status'))
                audit(event='response_end',request_id=rid,completed=complete,usage=usage,response_id=response_id,elapsed_seconds=time.monotonic()-started)
                self.close_connection=True
        except Exception as e:
            audit(event='bridge_error',request_id=rid,error_type=type(e).__name__,elapsed_seconds=time.monotonic()-started)
            if not sent:
                try: self.reply(502,{'error':{'message':type(e).__name__}})
                except OSError: pass
            self.close_connection=True
ThreadingHTTPServer(('127.0.0.1',C['bridgePort']),Handler).serve_forever()
