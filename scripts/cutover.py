"""Drain generation, retain scored/submitted work, replace only the scheduler."""
import argparse
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import time

parser=argparse.ArgumentParser()
parser.add_argument('--scheduler-release',required=True)
parser.add_argument('--workers',type=int,choices=(2,4),required=True)
args=parser.parse_args()
root=Path('/datadisk/agh-rsi')
state=json.loads((root/'control/supervisor.json').read_text())
supervisor=state['pid']
experiment=Path(state['release'])
processes=[]
for proc in Path('/proc').iterdir():
    if proc.name.isdigit():
        try:
            status=(proc/'status').read_text()
            ppid=int(next(s for s in status.splitlines() if s.startswith('PPid:')).split()[1])
            command=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode()
            if ppid==supervisor and 'src/rsi.py' in command:
                processes.append(int(proc.name))
        except (OSError,StopIteration):
            pass
if len(processes)!=1:
    raise RuntimeError('Cannot uniquely identify active scheduler')
scheduler=processes[0]
deadline=time.monotonic()+2100
while True:
    with sqlite3.connect(root/'control/runs.sqlite') as db:
        running=db.execute("SELECT COUNT(*) FROM attempts WHERE state='running'").fetchone()[0]
    if not running:
        os.kill(scheduler,signal.SIGSTOP)
        with sqlite3.connect(root/'control/runs.sqlite') as db:
            if db.execute("SELECT COUNT(*) FROM attempts WHERE state='running'").fetchone()[0]:
                os.kill(scheduler,signal.SIGCONT)
            else:
                break
    if time.monotonic()>deadline:
        raise RuntimeError('Drain timeout: existing experiment left running')
    time.sleep(0.1)
with sqlite3.connect(root/'control/runs.sqlite') as db:
    completed=db.execute("SELECT id,state,success FROM attempts WHERE state='evaluated'").fetchall()
receipt={'time':time.time(),'previous_workers':state.get('workers',1),'new_workers':args.workers,
         'experiment_release':str(experiment),'scheduler_release':args.scheduler_release,
         'preserved_evaluated':completed,'per_attempt_cpu':8,'per_attempt_memory_gib':24,
         'reason':'explicit user request for four workers; scheduler-only amendment'}
amendments=root/'amendments'
amendments.mkdir(exist_ok=True)
(amendments/f'workers-{int(time.time())}.json').write_text(json.dumps(receipt,indent=2))
# No Agent generation is active; a submitted program can be independently re-evaluated.
os.kill(scheduler,signal.SIGKILL)
for _ in range(100):
    if not Path('/proc',str(supervisor)).exists():
        break
    time.sleep(0.1)
names=subprocess.check_output(['docker','ps','--format','{{.Names}}'],text=True).splitlines()
for name in names:
    if name.startswith(('rsi-exec-','rsi-grade-')):
        subprocess.run(['docker','rm','-f',name],capture_output=True)
with (root/'control/supervise.log').open('ab') as log:
    new=subprocess.Popen([str(root/'venv/bin/python'),args.scheduler_release+'/src/supervise.py',
        '--config',str(experiment/'config/remote.json'),'--experiment-release',str(experiment),
        '--workers',str(args.workers)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps({'new_supervisor_pid':new.pid,'workers':args.workers,'preserved_evaluated':len(completed)}),flush=True)
