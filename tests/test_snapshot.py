import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


class SnapshotTests(unittest.TestCase):
    def test_wal_source_produces_self_contained_verified_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'control').mkdir()
            source=sqlite3.connect(root/'control/runs.sqlite')
            try:
                source.execute('PRAGMA journal_mode=WAL')
                source.execute('CREATE TABLE attempts(task INTEGER,phase TEXT,repeat INTEGER,state TEXT,success INTEGER,started REAL)')
                source.execute('INSERT INTO attempts VALUES(3,"pilot",1,"evaluated",1,1)')
                source.commit()
                script=Path(__file__).resolve().parents[1]/'src/snapshot.py'
                subprocess.run([sys.executable,str(script),str(root)],check=True)
                exported=root/'exports/state'
                manifest=json.loads((exported/'FILES.json').read_text())
                self.assertFalse(any(name.endswith(('-wal','-shm','-journal','.tmp')) for name in manifest))
                for name,digest in manifest.items():
                    self.assertEqual(hashlib.sha256((exported/name).read_bytes()).hexdigest(),digest)
                copy=sqlite3.connect(exported/'runs.sqlite')
                try:
                    self.assertEqual(copy.execute('SELECT success FROM attempts').fetchone()[0],1)
                    self.assertEqual(copy.execute('PRAGMA journal_mode').fetchone()[0],'delete')
                finally:
                    copy.close()
            finally:
                source.close()
