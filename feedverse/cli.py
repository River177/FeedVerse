import argparse,json,time
from .backend import Backend,DEFAULT_ROOT

def main():
    p=argparse.ArgumentParser(); p.add_argument('--root',default=str(DEFAULT_ROOT)); p.add_argument('command',choices=['prepare','dataset','create','source','patch','train','status','cancel','evaluate','compare','case','select','heldout','_job','mcp','audit']); p.add_argument('args',nargs='*'); a=p.parse_args(); b=Backend(a.root); args=a.args
    if a.command=='prepare': result=b.initialize(args[0])
    elif a.command=='dataset': result=b.inspect_dataset()
    elif a.command=='create': result=b.create_variant(args[0],args[1] if len(args)>1 else 'baseline')
    elif a.command=='source': result=b.read_source(args[0])
    elif a.command=='patch': result=b.patch_source(args[0],open(args[1]).read())
    elif a.command=='train': result=b.train_variant(args[0])
    elif a.command=='status': result=b.get_job_status(args[0])
    elif a.command=='cancel': result=b.cancel(args[0])
    elif a.command=='evaluate': result=b.evaluate_variant(args[0])
    elif a.command=='compare': result=b.compare_runs(args)
    elif a.command=='case': result=b.recommend_case(args[0],int(args[1]) if len(args)>1 else 0)
    elif a.command=='select': result=b.select()
    elif a.command=='heldout': result=b.evaluate_variant(args[0],'heldout')
    elif a.command=='_job': return b.run_job(args[0])
    elif a.command=='mcp':
        from .mcp import serve
        return serve(b)
    elif a.command=='audit':
        from .audit import audit
        result=audit(b)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
