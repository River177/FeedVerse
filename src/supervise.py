"""One locked experiment process; validates preparation before enabling the queue."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import time
import urllib.request

from rsi import write


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    root = Path(config['root'])
    release = Path(__file__).resolve().parent.parent
    control = root / 'control'
    control.mkdir(parents=True, exist_ok=True)
    lock = (control / 'experiment.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = {'pid': os.getpid(), 'started': time.time(), 'release': str(release)}
    bridge = None
    try:
        state['stage'] = 'preflight'
        write(control / 'supervisor.json', state)
        database = control / 'runs.sqlite'
        if database.exists():
            with sqlite3.connect(database) as db:
                db.execute("UPDATE attempts SET state='infra_error',error='supervisor_interrupted',ended=? WHERE state='running'", (time.time(),))
        actual = subprocess.check_output(['git','-C',config['agh_source'],'rev-parse','HEAD'], text=True).strip()
        if actual != config['agh_commit']:
            raise RuntimeError('AGH commit mismatch')
        if subprocess.check_output(['git','-C',config['agh_source'],'status','--porcelain'],text=True).strip():
            raise RuntimeError('AGH source contains uncommitted changes')
        manifest = json.loads((root / 'assets/manifest.json').read_text())
        image = subprocess.check_output(['docker','image','inspect',config['image'],'--format','{{.Id}}'],text=True).strip()
        if manifest.get('image_id') != image:
            raise RuntimeError('Scientific image identity mismatch')
        (root / 'exports').mkdir(exist_ok=True)
        with (control / 'bridge.log').open('ab') as log:
            bridge = subprocess.Popen([config['python'], str(release / 'src/bridge.py'), '--config', args.config],
                                      stdout=log, stderr=subprocess.STDOUT)
        for _ in range(30):
            if bridge.poll() is not None:
                raise RuntimeError('Bridge startup failed')
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{config['port']}/health",timeout=2) as response:
                    if json.load(response)['deployment'] == config['deployment']:
                        break
            except OSError:
                time.sleep(1)
        else:
            raise RuntimeError('Gateway readiness timeout')
        state['stage'] = 'validation_then_full_experiment'
        write(control / 'supervisor.json', state)
        with (control / 'experiment.log').open('ab') as log:
            result = subprocess.run([config['python'],str(release/'src/rsi.py'),'--config',args.config,'all'],
                                    stdout=log,stderr=subprocess.STDOUT)
        state.update(stage='complete' if result.returncode == 0 else 'stopped_on_error',
                     exit_code=result.returncode,ended=time.time())
        write(control / 'supervisor.json', state)
        return result.returncode
    except Exception as error:
        state.update(stage='stopped_on_error',error_type=type(error).__name__,error=str(error),ended=time.time())
        write(control / 'supervisor.json', state)
        raise
    finally:
        if bridge:
            bridge.terminate()
            try:
                bridge.wait(timeout=10)
            except subprocess.TimeoutExpired:
                bridge.kill()


if __name__ == '__main__':
    raise SystemExit(main())
