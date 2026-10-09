"""Consistent read snapshots for backup; does not change experiment identity or scores."""
import hashlib
from contextlib import closing
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import time

root = Path(sys.argv[1])
destination = root / 'exports/state'
destination.mkdir(parents=True, exist_ok=True)
for name in ('runs.sqlite','usage.sqlite'):
    source = root / 'control' / name
    if source.exists():
        temp = destination / (name + '.tmp')
        with closing(sqlite3.connect(f'file:{source}?mode=ro', uri=True)) as original:
            with closing(sqlite3.connect(temp)) as copy:
                original.backup(copy)
                copy.execute('PRAGMA journal_mode=DELETE')
                copy.commit()
        temp.replace(destination / name)
for source in [root/'control/supervisor.json', root/'assets/manifest.json', root/'split_manifest.json', root/'protocol.json']:
    if source.exists():
        shutil.copyfile(source, destination / source.name)
state = {'time': time.time(), 'experiment_state': None, 'attempt_states': {}}
database = destination / 'runs.sqlite'
if database.exists():
    with closing(sqlite3.connect(f'file:{database}?mode=ro',uri=True)) as db:
        state['attempt_states'] = dict(db.execute('SELECT state,COUNT(*) FROM attempts GROUP BY state').fetchall())
        state['latest'] = db.execute('SELECT task,phase,repeat,state,success FROM attempts ORDER BY started DESC LIMIT 3').fetchall()
if (root / 'control/supervisor.json').exists():
    state['experiment_state'] = json.loads((root/'control/supervisor.json').read_text())
(destination/'status.json').write_text(json.dumps(state, indent=2))
files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in destination.iterdir()
         if p.is_file() and p.name not in ('FILES.json','FILES.json.tmp')
         and not p.name.endswith(('.tmp','-wal','-shm','-journal'))}
temp = destination / 'FILES.json.tmp'
temp.write_text(json.dumps(files, indent=2))
temp.replace(destination / 'FILES.json')
