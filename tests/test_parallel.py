from pathlib import Path
import sys
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from rsi import parallel_jobs


class ParallelTests(unittest.TestCase):
    def test_bounded_four_workers_execute_each_job_once(self):
        lock=threading.Lock()
        active=0
        peak=0
        seen=[]
        def work(job):
            nonlocal active,peak
            with lock:
                active+=1
                peak=max(peak,active)
                seen.append(job)
            time.sleep(0.02)
            with lock:
                active-=1
            return job*2
        result=parallel_jobs(list(range(12)),work,4)
        self.assertEqual(sorted(seen),list(range(12)))
        self.assertEqual(sorted(result),[i*2 for i in range(12)])
        self.assertEqual(peak,4)

    def test_error_stops_new_dispatch(self):
        seen=[]
        def work(job):
            seen.append(job)
            if job==0:
                raise RuntimeError('auth_error')
            time.sleep(0.05)
        with self.assertRaisesRegex(RuntimeError,'auth_error'):
            parallel_jobs(list(range(100)),work,4)
        self.assertLessEqual(len(seen),4)
