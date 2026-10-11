"""Loopback web API. Model tools and evaluation labels have separate access paths."""
import asyncio,json,os,time,uuid
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI,HTTPException,Request,Query
from fastapi.responses import StreamingResponse,FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field,ConfigDict
from .backend import PROJECT
from .web_store import Store,HISTORY_ID,ACTIVE,TERMINAL,redact,read_json
from .web_runner import launch

class ExplorationRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    title:str=Field(min_length=1,max_length=100)
    instruction:str=Field(min_length=1,max_length=2000)
    candidate_limit:int=Field(default=3,ge=1,le=3)
    request_key:str=Field(min_length=8,max_length=100)

def create_app(store=None,launcher=launch):
    store=store or Store()
    @asynccontextmanager
    async def lifespan(app):
        store.reconcile();yield
    app=FastAPI(title='FeedVerse local API',lifespan=lifespan)
    app.state.store=store
    @app.middleware('http')
    async def local_boundary(request:Request,call_next):
        # Browser requests use same-origin proxy. External-origin writes cannot start a model session.
        if request.method not in ['GET','HEAD','OPTIONS']:
            origin=request.headers.get('origin')
            if origin and origin not in ['http://127.0.0.1:5173','http://localhost:5173','http://127.0.0.1:18779','http://localhost:18779']:return JSONResponse({'detail':'Local same-origin requests only'},status_code=403)
        return await call_next(request)
    @app.exception_handler(ValueError)
    async def invalid(request,exc):return JSONResponse({'detail':str(exc)},status_code=404)
    @app.exception_handler(FileNotFoundError)
    async def unavailable(request,exc):return JSONResponse({'detail':'实验产物尚未就绪'},status_code=409)
    @app.get('/api/health')
    def health():
        ready=(store.history/'audit.json').exists() and read_json(store.history/'audit.json',{}).get('passed',False)
        current=next((r['id'] for r in store.listing() if r['status'] in ACTIVE),None)
        services=read_json(store.path(current)/'runtime/services.json',{'agh':'preparing','bridge':'preparing','mcp':'preparing'}) if current else {'agh':'idle','bridge':'idle','mcp':'idle'}
        return {'services':services,'product':'FeedVerse','api':'ready','data':'ready' if ready else 'missing','sandbox':'verified' if read_json(store.history/'isolation-receipt.json',{}).get('blocked')=={'read':True,'write':True,'network':True} else 'unchecked','agh_build':'ready' if (PROJECT/'local/agh-pinned/packages/cli/dist/local/agnes.mjs').exists() else 'missing','active':current,'model':'gpt-6-astra_2026-09-03','credentials':'server-only'}
    @app.get('/api/experiments')
    def experiments():return store.listing()
    @app.post('/api/explorations')
    def create(body:ExplorationRequest):
        if not (store.history/'audit.json').exists():raise HTTPException(503,'Frozen baseline unavailable')
        row,new=store.create(body.title.strip(),body.instruction.strip(),body.candidate_limit,body.request_key)
        if new:
            try:row=launcher(store,row['id'])
            except Exception as exc:store.update(row['id'],status='failed',error=str(exc));raise HTTPException(503,'Exploration startup failed')
        return {'id':row['id'],'status':row['status'],'created':new}
    @app.get('/api/experiments/{eid}')
    def snapshot(eid:str):return store.snapshot(eid)
    @app.post('/api/explorations/{eid}/cancel')
    def cancel(eid:str):
        row=store.get(eid)
        if row['status'] in ['preparing','running']:store.update(eid,status='cancelling');store.event(eid,'lifecycle','cancel-request:'+str(time.time()),'lifecycle','请求停止 AGH 与训练',{})
        return store.get(eid)
    @app.post('/api/explorations/{eid}/resume')
    def resume(eid:str):
        store.reconcile();row=store.get(eid)
        if row['status']=='completed' or row['status'] in ACTIVE:return row
        # Atomic reservation prevents concurrent resumes or overlap with another exploration.
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            other=db.execute("SELECT id FROM explorations WHERE status IN ('preparing','running','cancelling') AND id<>?",(eid,)).fetchone()
            if other:raise HTTPException(409,'Another exploration is active')
            current=db.execute('SELECT status FROM explorations WHERE id=?',(eid,)).fetchone()['status']
            if current in ACTIVE:return store.get(eid)
            db.execute("UPDATE explorations SET status='preparing',updated=? WHERE id=?",(time.time(),eid))
        return launcher(store,eid)
    @app.get('/api/experiments/{eid}/events')
    async def events(eid:str,request:Request,after:int=0):
        if eid!=HISTORY_ID:store.get(eid)
        cursor=max(after,int(request.headers.get('last-event-id','0')))
        async def stream():
            nonlocal cursor
            while not await request.is_disconnected():
                await asyncio.to_thread(store.ingest,eid)
                rows=store.events(eid,cursor)
                for row in rows:
                    cursor=row['seq'];yield f"id: {cursor}\ndata: {json.dumps(row,ensure_ascii=False)}\n\n"
                if not rows:yield ': heartbeat\n\n'
                await asyncio.sleep(1)
        return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})
    @app.get('/api/experiments/{eid}/event-log')
    def log(eid:str,after:int=0,limit:int=Query(300,ge=1,le=1000)):
        if eid!=HISTORY_ID:store.get(eid)
        store.ingest(eid);return {'items':store.events(eid,after,limit),'last_seq':store.event_max(eid)}
    @app.get('/api/experiments/{eid}/models/{variant}/source')
    def source(eid:str,variant:str):return store.view(eid).source(variant)
    @app.get('/api/experiments/{eid}/cases')
    def cases(eid:str,q:str='',cold:bool=False,page:int=Query(0,ge=0),size:int=Query(20,ge=1,le=100)):return store.view(eid).cases(q,cold,page,size)
    @app.get('/api/experiments/{eid}/cases/{index}')
    def case(eid:str,index:int,variant:str='baseline'):return store.view(eid).case(index,variant)
    @app.get('/api/experiments/{eid}/distribution')
    def distribution(eid:str,variant:str='baseline'):return store.view(eid).distribution(variant)
    @app.get('/api/experiments/{eid}/articles/{article}')
    def article(eid:str,article:str):
        _,news,seen=store.view(eid).data()
        if article not in news:raise HTTPException(404,'Unknown article')
        return {'id':article,**news[article],'cold':article not in seen}
    @app.get('/api/experiments/{eid}/export')
    def export(eid:str):
        snapshot=store.snapshot(eid);items=[];after=0
        while True:
            chunk=store.events(eid,after,1000)
            if not chunk:break
            items+=chunk;after=chunk[-1]['seq']
        value={'product':'FeedVerse','snapshot':snapshot,'events':items,'exported_at':time.time()}
        return JSONResponse(redact(value),headers={'Content-Disposition':f'attachment; filename="feedverse-{eid}.json"'})
    # Keep static assets separate from /api; SPA fallback serves both the real app and /prototype.
    dist=PROJECT/'dist'
    if (dist/'assets').exists():app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
    @app.get('/{path:path}')
    def spa(path:str):
        if path.startswith('api/'):raise HTTPException(404,'Unknown API route')
        if (dist/'index.html').exists():return FileResponse(dist/'index.html')
        raise HTTPException(503,'Run the Vite development server or npm run build')
    return app

app=create_app()
