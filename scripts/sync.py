"""Copy durable exports to the Mac, then independently verify remote file hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time


def sync(destination, snapshot=None):
    destination.mkdir(parents=True, exist_ok=True)
    if snapshot:
        subprocess.run(['ssh','-o','BatchMode=yes','gcr-a100',
            '/datadisk/agh-rsi/venv/bin/python',snapshot,'/datadisk/agh-rsi'],check=True)
    subprocess.run(['rsync', '-a', 'gcr-a100:/datadisk/agh-rsi/exports/', str(destination) + '/'], check=True)
    verified = 0
    for manifest in destination.glob('*/FILES.json'):
        for name, expected in json.loads(manifest.read_text()).items():
            target = manifest.parent / name
            if not target.is_file():
                raise RuntimeError('Backup file missing: ' + str(target))
            digest = hashlib.sha256()
            with target.open('rb') as f:
                for chunk in iter(lambda:f.read(1024*1024), b''):
                    digest.update(chunk)
            if digest.hexdigest() != expected:
                raise RuntimeError('Backup checksum mismatch: ' + str(target))
            verified += 1
    (destination / 'BACKUP_VERIFIED.json').write_text(json.dumps({'verified_files':verified,'time':time.time()}))
    return verified


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--destination',default=str(Path(__file__).resolve().parents[1]/'runs'/'remote-backup'))
    parser.add_argument('--watch',action='store_true')
    parser.add_argument('--snapshot',help='Pinned remote snapshot.py path, independent of the experiment deployment')
    args=parser.parse_args()
    while True:
        try:
            print(json.dumps({'verified_files':sync(Path(args.destination),args.snapshot)}),flush=True)
        except Exception as error:
            print(json.dumps({'error':type(error).__name__,'message':str(error)}),flush=True)
            if not args.watch:
                raise
        if not args.watch:
            break
        time.sleep(45)
