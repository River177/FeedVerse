import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from bridge import connect, inspect_event, register, reserve, finish
from rsi import decision, split_tasks, success_counts


def panel(counts):
    return [{'task': task, 'repeat': repeat, 'state': 'evaluated',
             'success': int(repeat <= count)}
            for task, count in counts.items() for repeat in (1,2,3)]


class ProtocolTests(unittest.TestCase):
    def test_request_cap_includes_inflight_and_failed_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'usage.sqlite'
            register(db, 'private-test-key', 'a', 2)
            first = reserve(db, 'private-test-key')
            finish(db, first, 'bridge_error')
            reserve(db, 'private-test-key')
            with self.assertRaises(OverflowError):
                reserve(db, 'private-test-key')
            with self.assertRaises(PermissionError):
                reserve(db, 'invalid-key')
            with connect(db) as connection:
                self.assertNotIn('private-test-key', str(connection.execute('SELECT * FROM keys').fetchall()))

    def test_stream_end_is_not_completion(self):
        self.assertEqual(inspect_event({'type': 'response.output_text.done'})[0], None)
        event = {'type': 'response.completed', 'response': {'id': 'r', 'usage': {'total_tokens': 7}}}
        self.assertEqual(inspect_event(event), ('completed', 'r', {'total_tokens': 7}))
        self.assertEqual(inspect_event({'type': 'response.incomplete'})[0], 'response.incomplete')

    def test_strict_acceptance(self):
        self.assertTrue(decision(panel({1:1,2:3}), panel({1:2,2:3}))['eligible'])
        self.assertFalse(decision(panel({1:1,2:3}), panel({1:3,2:2}))['eligible'])
        self.assertFalse(decision(panel({1:1}), panel({1:1}))['eligible'])

    def test_missingness_and_duplicates_block_acceptance(self):
        before, after = panel({1:1}), panel({1:3})
        after[0]['state'] = 'infra_error'
        after[0]['success'] = None
        self.assertFalse(decision(before, after)['coverage_complete'])
        self.assertFalse(success_counts(before + [before[0]])[1])
        self.assertFalse(decision(before, panel({1:3,2:3}))['eligible'])
        self.assertFalse(success_counts([])[1])

    def test_split_groups_shared_sources_and_pilot_without_score(self):
        tasks = [dict(instance_id=i, github_name=repo, dataset_folder_tree=f'|-- {data}/\n|---- x.csv')
                 for i,repo,data in [(1,'a','x'),(2,'a','y'),(3,'b','z'),(4,'c','z'),(5,'d','q'),(6,'e','v')]]
        first = split_tasks(tasks,3,20261009)
        self.assertEqual(first,split_tasks(tasks,3,20261009))
        self.assertIn(3,first['development'])
        for group in first['groups']:
            self.assertTrue(set(group)<=set(first['development']) or set(group)<=set(first['holdout']))
        self.assertEqual(set(first['development'])|set(first['holdout']),set(range(1,7)))
        self.assertFalse(set(first['development'])&set(first['holdout']))


if __name__ == '__main__':
    unittest.main()
