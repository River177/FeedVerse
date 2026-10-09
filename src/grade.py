"""Runs only in the evaluator container, AFTER isolated solution execution."""
import importlib.util
import json
import os
from pathlib import Path
import sys

task = json.loads(Path('/control/task.json').read_text())
os.chdir('/testbed')
sys.path.insert(0, '/testbed')
sys.path.insert(0, '/official')
script = Path('/testbed/benchmark/eval_programs') / task['eval_script_name']
spec = importlib.util.spec_from_file_location('official_task_evaluator', script)
module = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(module)
    success, details = module.eval()
    result = {'success': int(success), 'official_evaluator': task['eval_script_name'],
              'details': str(details), 'evaluation_valid': True}
except Exception as error:
    result = {'success': None, 'evaluation_valid': False, 'error_type': type(error).__name__,
              'error': str(error)[:2000]}
Path('/control/grade.json').write_text(json.dumps(result, indent=2))
print(json.dumps({k: v for k, v in result.items() if k != 'details'}))
