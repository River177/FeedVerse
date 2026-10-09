"""Single-agent scientific runner and conservative strategy evolution CLI."""
import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import re
import secrets
import shutil
import sqlite3
import statistics
import subprocess
import time
import uuid

from bridge import connect, register


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def object_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False))
    temporary.replace(path)


def read(path):
    return json.loads(Path(path).read_text())


def check(root):
    root = Path(root)
    (root / 'control').mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(root / 'control' / 'runs.sqlite', timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('''CREATE TABLE IF NOT EXISTS attempts (
        id TEXT PRIMARY KEY, identity TEXT UNIQUE, task INTEGER, strategy TEXT, config TEXT,
        phase TEXT, repeat INTEGER, state TEXT, success INTEGER, valid INTEGER,
        started REAL, ended REAL, path TEXT, error TEXT)''')
    return db


def data_folders(task):
    folders = re.findall(r'^\|--\s+([^/\n]+)', task['dataset_folder_tree'] or '', re.M)
    if not folders or any(not re.fullmatch(r'[\w .-]+', f) for f in folders):
        raise ValueError(f"Cannot safely resolve datasets for {task['instance_id']}")
    return folders


def split_tasks(tasks, target, seed, required=(3,)):
    """Conservative components: shared repository OR dataset never crosses split."""
    parent = {int(t['instance_id']): int(t['instance_id']) for t in tasks}
    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    seen = {}
    for task in tasks:
        i = int(task['instance_id'])
        keys = [('data', f) for f in data_folders(task)]
        if task.get('github_name'):
            keys.append(('repo', task['github_name'].strip().lower()))
        for key in keys:
            if key in seen:
                parent[find(i)] = find(seen[key])
            seen[key] = i
    groups = defaultdict(list)
    for t in tasks:
        groups[find(int(t['instance_id']))].append(int(t['instance_id']))
    groups = sorted([sorted(g) for g in groups.values()])
    forced = [g for g in groups if set(g) & set(required)]
    other = [g for g in groups if not set(g) & set(required)]
    random.Random(seed).shuffle(other)
    # Seed fixes ties. Choose closest feasible task count while preserving components.
    initial = tuple(i for g in forced for i in g)
    choices = {len(initial): initial}
    for group in other:
        for count, ids in list(choices.items()):
            new = count + len(group)
            if new not in choices:
                choices[new] = ids + tuple(group)
    count = min((n for n in choices if n < len(tasks)), key=lambda n: (abs(n-target), n))
    dev = sorted(choices[count])
    return {'seed': seed, 'group_rule': 'shared github repository OR dataset connected components',
            'groups': groups, 'development': dev, 'holdout': sorted(set(parent) - set(dev)),
            'pilot_tasks_forced_into_development': list(required)}


class Runner:
    def __init__(self, config, release):
        self.config = config
        self.release = Path(release).resolve()
        self.root = Path(config['root'])
        self.db = check(self.root)
        self.usage_db = self.root / 'control' / 'usage.sqlite'
        self.manifest = read(self.root / 'assets' / 'manifest.json')
        self.benchmark = Path(self.manifest['benchmark_path'])
        self.tasks = {int(t['instance_id']): t for t in read(self.root / 'assets' / 'tasks.json')}
        self.image = self.manifest.get('image_id') or config['image']
        self.config_hash = object_hash({'config': config, 'manifest': self.manifest,
                                       'release': (self.release / 'DEPLOYMENT.json').read_text()})

    def command(self, args, log, timeout):
        with Path(log).open('wb') as out:
            try:
                return subprocess.run(args, stdout=out, stderr=subprocess.STDOUT,
                                      timeout=timeout).returncode
            except subprocess.TimeoutExpired:
                return 124

    def docker(self, workspace, name, network='none'):
        return ['docker', 'run', '--name', name, '--rm', '--network', network,
                '--cap-drop=ALL', '--security-opt=no-new-privileges', '--pids-limit', '512',
                '--memory', '24g', '--cpus', '8', '-v', f'{workspace}:/workspace', '-w', '/workspace']

    def worker_mounts(self, path):
        cfg = self.config
        return ['-v', f"{cfg['agh_source']}:{cfg['agh_source']}:ro",
                '-v', f"{cfg['node_root']}:/opt/node:ro", '-v', f'{path}/control:/control',
                '-v', f'{self.release}/src/worker.mjs:/runner/worker.mjs:ro',
                '-e', 'PATH=/opt/node/bin:/opt/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                '-e', 'AGH_HOME=/control/home', '-e', 'HOME=/control/home',
                '-e', 'PYTHONUNBUFFERED=1', '-e', 'OMP_NUM_THREADS=4']

    def revoke(self, attempt):
        with connect(self.usage_db) as db:
            db.execute('DELETE FROM keys WHERE attempt=?', (attempt,))

    def usage(self, attempt):
        with connect(self.usage_db) as db:
            db.row_factory = sqlite3.Row
            rows = [dict(r) for r in db.execute('SELECT * FROM requests WHERE attempt=? ORDER BY started', (attempt,))]
        total = Counter()
        for r in rows:
            if r['usage']:
                usage = json.loads(r['usage'])
                for k in ('input_tokens', 'output_tokens', 'total_tokens'):
                    total[k] += usage.get(k, 0)
                r['usage'] = usage
        return {'requests': rows, 'totals': dict(total),
                'missing_usage': sum(r['usage'] is None for r in rows), 'price_source': None}

    def publish(self, path, task=None):
        destination = self.root / 'exports' / path.name
        destination.mkdir(parents=True, exist_ok=True)
        candidates = list(path.glob('*.json')) + list(path.glob('*.log')) + list(path.glob('solution.py'))
        for name in ('session.json','turn.json','error.json','trace.jsonl','permissions.jsonl'):
            candidate = path / 'control' / name
            if candidate.exists():
                candidates.append(candidate)
        for source in candidates:
            target = destination / source.relative_to(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        if task:
            source = path / 'independent' / task['output_fname']
            if source.is_file() and not source.is_symlink():
                target = destination / 'output' / source.name
                target.parent.mkdir(exist_ok=True)
                shutil.copyfile(source, target)
        write(destination / 'FILES.json', {str(f.relative_to(destination)): sha(f)
            for f in destination.rglob('*') if f.is_file() and f.name not in ('FILES.json','FILES.json.tmp')})

    def publish_reports(self):
        destination = self.root / 'exports' / 'reports'
        destination.mkdir(parents=True, exist_ok=True)
        for name in ('protocol.json','final-strategy.json','completion.json'):
            source = self.root / name
            if source.exists():
                shutil.copyfile(source, destination / name)
        if (self.root / 'reports').exists():
            shutil.copytree(self.root / 'reports', destination / 'results', dirs_exist_ok=True)
        if (self.root / 'strategies').exists():
            shutil.copytree(self.root / 'strategies', destination / 'strategies', dirs_exist_ok=True)
        write(destination / 'FILES.json', {str(f.relative_to(destination)): sha(f)
            for f in destination.rglob('*') if f.is_file() and f.name not in ('FILES.json','FILES.json.tmp')})

    def attempt(self, task_id, strategy, phase, repeat, smoke=False):
        task = self.tasks.get(task_id) if not smoke else None
        strategy = Path(strategy)
        strategy_hash = sha(strategy)
        identity = object_hash([task_id, strategy_hash, self.config_hash, phase, repeat])
        base_identity = identity
        old = self.db.execute('SELECT * FROM attempts WHERE identity=? OR identity LIKE ? ORDER BY started DESC LIMIT 1',
                              (identity, identity + ':retry%')).fetchone()
        if old:
            if old['state'] in ('submitted', 'evaluated', 'task_failed', 'budget_exhausted'):
                return dict(old)
            if old['state'] == 'running':
                # Preserve interrupted receipts; never reuse their partial files.
                self.db.execute('UPDATE attempts SET state=?,error=?,ended=? WHERE id=?',
                                ('infra_error', 'interrupted_attempt', time.time(), old['id']))
                self.db.commit()
                self.revoke(old['id'])
            retries = self.db.execute('SELECT COUNT(*) FROM attempts WHERE identity LIKE ?',
                                      (base_identity + ':retry%',)).fetchone()[0]
            if old['error'] == 'auth_error' or retries >= 2:
                return dict(self.db.execute('SELECT * FROM attempts WHERE id=?', (old['id'],)).fetchone())
            identity = base_identity + f':retry{retries+1}'
        attempt = f'{phase}-t{task_id}-r{repeat}-{uuid.uuid4().hex[:10]}'
        path = self.root / 'runs' / attempt
        workspace = path / 'workspace'
        control = path / 'control'
        workspace.mkdir(parents=True)
        control.mkdir()
        (control / 'home').mkdir()
        metadata = {'attempt_id': attempt, 'task_id': task_id, 'strategy_sha256': strategy_hash,
                    'config_sha256': self.config_hash, 'phase': phase, 'repeat': repeat,
                    'deployment': self.config['deployment'], 'api_version': self.config['api_version'],
                    'thinking': self.config['thinking'], 'image_id': self.image,
                    'dataset_revision': self.config['dataset_revision'], 'started': time.time()}
        write(path / 'identity.json', metadata)
        self.db.execute('INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (attempt, identity, task_id, strategy_hash, self.config_hash, phase, repeat,
                         'running', None, None, time.time(), None, str(path), None))
        self.db.commit()
        mounts = []
        if smoke:
            (workspace / 'measurements.csv').write_text('sample_id,temperature_c\n1,10\n2,12\n3,14\n')
            prompt = ('Read measurements.csv with a file tool. Write solution.py using csv, statistics, json. '
                      'Compute count, mean_temperature_c, sample_sd_temperature_c; save result.json and print it. '
                      'Execute shell with exactly python3 solution.py. Read result.json with a file tool. '
                      'No other shell commands, package installations, network or subagents.')
        else:
            for folder in data_folders(task):
                source = self.benchmark / 'datasets' / folder
                if not source.is_dir():
                    raise FileNotFoundError(source)
                destination = workspace / 'benchmark' / 'datasets' / folder
                destination.mkdir(parents=True)
                mounts += ['-v', f'{source}:/workspace/benchmark/datasets/{folder}:ro']
            prompt = ('Complete this scientific task using real tools in /workspace. Deliver solution.py, '
                      'a standalone Python program that regenerates the required outputs from the provided data. '
                      'Use benchmark/datasets/ as the data root. Do not use subagents or search for answers.\n\n'
                      + task['task_inst'] + '\n\nExpert knowledge:\n' + (task.get('domain_knowledge') or '')
                      + '\n\nData tree:\n' + task['dataset_folder_tree']
                      + '\n\nPreview:\n' + (task.get('dataset_preview') or '')
                      + '\n\nExecution strategy:\n' + strategy.read_text())
        key = secrets.token_urlsafe(32)
        register(self.usage_db, key, attempt, self.config['task_request_limit'])
        write(control / 'input.json', {**{k: self.config[k] for k in (
            'agh_source', 'port', 'model', 'thinking', 'context_window', 'task_timeout_seconds', 'preset')},
            'key': key, 'prompt': prompt, 'smoke': smoke})
        os.chmod(control / 'input.json', 0o600)
        name = 'rsi-' + uuid.uuid4().hex[:16]
        print(json.dumps({'event': 'attempt_started', 'attempt': attempt}), flush=True)
        args = self.docker(workspace, name, 'host') + mounts + self.worker_mounts(path)
        args += [self.image, '/opt/node/bin/node', '/runner/worker.mjs']
        rc = self.command(args, path / 'worker.log', self.config['task_timeout_seconds'] + 90)
        if rc == 124:
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
        self.revoke(attempt)
        usage = self.usage(attempt)
        write(path / 'usage.json', usage)
        # Remove local bearer from durable/exported inputs and AGH provider configuration.
        (control / 'input.json').unlink(missing_ok=True)
        for secret_file in (control / 'home').rglob('configuration.json'):
            secret_file.unlink()
        program = workspace / 'solution.py'
        state, error = 'infra_error', None
        turn = read(control / 'turn.json').get('turn', {}) if (control / 'turn.json').exists() else {}
        requests = usage['requests']
        if any(r['status'] == 'auth_error' for r in requests):
            error = 'auth_error'
        elif len(requests) >= self.config['task_request_limit'] and turn.get('reason') != 'completed':
            state, error = 'budget_exhausted', 'request_limit'
        elif rc == 124 or turn.get('reason') == 'aborted':
            state, error = 'budget_exhausted', 'time_limit'
        elif rc == 0 and turn.get('reason') == 'completed' and program.is_file() and not program.is_symlink():
            state = 'submitted'
            metadata['program_sha256'] = sha(program)
            shutil.copyfile(program, path / 'solution.py')
        elif requests and all(r['status'] == 'completed' for r in requests):
            state, error = 'task_failed', 'missing_submission_or_incomplete_turn'
        else:
            error = 'worker_or_gateway_error'
        if smoke and state == 'submitted':
            output = read(workspace / 'result.json')
            expected = {'count': 3, 'mean_temperature_c': 12, 'sample_sd_temperature_c': 2}
            if output != expected:
                state, error = 'task_failed', 'independent_smoke_check_failed'
            else:
                write(path / 'smoke_check.json', {'passed': True, 'observed': output, 'expected': expected})
        metadata.update({'state': state, 'error': error, 'turn': turn, 'ended': time.time()})
        write(path / 'identity.json', metadata)
        self.db.execute('UPDATE attempts SET state=?,error=?,ended=? WHERE id=?', (state, error, time.time(), attempt))
        self.db.commit()
        print(json.dumps({'event': 'attempt_finished', 'attempt': attempt, 'state': state, 'error': error}), flush=True)
        self.publish(path)
        return dict(self.db.execute('SELECT * FROM attempts WHERE id=?', (attempt,)).fetchone())

    def evaluate(self, attempt):
        row = dict(self.db.execute('SELECT * FROM attempts WHERE id=?', (attempt,)).fetchone())
        if row['state'] == 'evaluated':
            return row
        if row['state'] != 'submitted':
            return row
        task = self.tasks[row['task']]
        path = Path(row['path'])
        identity = read(path / 'identity.json')
        if sha(path / 'solution.py') != identity['program_sha256']:
            raise ValueError('Submitted program hash changed')
        workspace = path / 'independent'
        workspace.mkdir(exist_ok=True)
        shutil.copyfile(path / 'solution.py', workspace / 'solution.py')
        mounts = []
        for folder in data_folders(task):
            destination = workspace / 'benchmark' / 'datasets' / folder
            destination.mkdir(parents=True, exist_ok=True)
            mounts += ['-v', f'{self.benchmark}/datasets/{folder}:/workspace/benchmark/datasets/{folder}:ro']
        image = self.instance_image(path, task)
        if image is None:
            self.db.execute('UPDATE attempts SET state=?,error=?,ended=? WHERE id=?',
                            ('infra_error', 'dependency_build_failed', time.time(), attempt))
            self.db.commit()
            self.publish(path)
            return dict(self.db.execute('SELECT * FROM attempts WHERE id=?', (attempt,)).fetchone())
        name = 'rsi-exec-' + uuid.uuid4().hex[:12]
        args = self.docker(workspace, name) + mounts + [image, 'python', 'solution.py']
        rc = self.command(args, path / 'execution.log', self.config['eval_timeout_seconds'])
        if rc == 124:
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
        output = workspace / task['output_fname']
        valid = rc == 0 and output.exists() and not output.is_symlink()
        if not valid:
            result = {'success': 0, 'valid_program': False, 'evaluation_valid': True,
                      'failure_category': 'execution_timeout' if rc == 124 else 'execution_or_output_failure'}
        else:
            # Generated code is NEVER executed with reference/evaluation mounts present.
            grade_control = path / 'grading'
            grade_control.mkdir(exist_ok=True)
            write(grade_control / 'task.json', task)
            name = 'rsi-grade-' + uuid.uuid4().hex[:12]
            args = ['docker', 'run', '--rm', '--name', name, '--network', 'none', '--cap-drop=ALL',
                    '--security-opt=no-new-privileges', '--memory', '24g', '--cpus', '8',
                    '-v', f'{workspace}:/testbed:ro', '-v', f'{self.benchmark}:/testbed/benchmark:ro',
                    '-v', f'{grade_control}:/control', '-v', f'{self.release}/src/grade.py:/grade.py:ro',
                    image, 'python', '/grade.py']
            rc = self.command(args, path / 'grading.log', self.config['eval_timeout_seconds'])
            if rc == 124:
                subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
            result = read(grade_control / 'grade.json') if (grade_control / 'grade.json').exists() else {
                'success': None, 'evaluation_valid': False, 'error_type': 'grading_process_error'}
            result['valid_program'] = True
        result.update({'program_sha256': identity['program_sha256'],
                       'official_evaluator_sha256': sha(self.benchmark / 'eval_programs' / task['eval_script_name'])})
        write(path / 'evaluation.json', result)
        state = 'evaluated' if result['evaluation_valid'] else 'infra_error'
        self.db.execute('UPDATE attempts SET state=?,success=?,valid=?,error=?,ended=? WHERE id=?',
                        (state, result['success'], int(valid), None if state == 'evaluated' else result.get('error_type'),
                         time.time(), attempt))
        self.db.commit()
        subprocess.run(['docker', 'image', 'rm', image], capture_output=True)
        print(json.dumps({'event': 'evaluation_finished', 'attempt': attempt, 'state': state,
                          'success': result['success']}), flush=True)
        self.publish(path, task)
        return dict(self.db.execute('SELECT * FROM attempts WHERE id=?', (attempt,)).fetchone())

    def instance_image(self, path, task):
        context = path / 'image-build'
        context.mkdir(exist_ok=True)
        repo = self.root / 'assets/ScienceAgentBench'
        spec = importlib.util.spec_from_file_location('official_dockerfiles', repo / 'evaluation/harness/dockerfiles.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        name = 'pred_' + task['gold_program_name']
        shutil.copyfile(path / 'solution.py', context / name)
        shutil.copyfile(repo / 'config_conda_env.py', context / 'config_conda_env.py')
        # Credentials are injected at runtime, never baked into an image.
        dockerfile = module.get_dockerfile_instance('linux/amd64', self.config['image'], name)
        (context / 'Dockerfile').write_text(dockerfile)
        tag = 'agh-rsi-attempt:' + path.name.lower()
        rc = self.command(['docker', 'build', '-t', tag, str(context)], path / 'dependency-build.log', 1800)
        if rc != 0:
            return None
        image_id = subprocess.check_output(['docker', 'image', 'inspect', tag, '--format', '{{.Id}}'], text=True).strip()
        write(path / 'environment.json', {'image_id': image_id, 'dockerfile_sha256': sha(context / 'Dockerfile'),
                                          'base_image_id': self.image})
        return tag

    def panel(self, tasks, strategy, phase, repeats=3):
        results = []
        for repeat in range(1, repeats+1):
            for task in tasks:
                row = self.attempt(task, strategy, phase, repeat)
                if row['error'] == 'auth_error':
                    raise RuntimeError('Authentication failed; queue stopped without relogin/model substitution')
                if row['state'] == 'submitted':
                    row = self.evaluate(row['id'])
                # At most two clean retries for technical failures, never for a scored failure.
                for _ in range(2):
                    if row['state'] != 'infra_error' or row['error'] == 'auth_error':
                        break
                    row = self.attempt(task, strategy, phase, repeat)
                    if row['state'] == 'submitted':
                        row = self.evaluate(row['id'])
                results.append(row)
        write(self.root / 'reports' / f'{phase}.json', results)
        self.publish_reports()
        return results

    def feedback(self, panel):
        package = []
        for row in panel:
            if row['state'] not in ('evaluated', 'task_failed', 'budget_exhausted'):
                continue
            entry = {'task_id': row['task'], 'attempt_id': row['id'], 'success': row['success'],
                     'state': row['state'], 'public_failure_category': row['error']}
            # Agent-owned commands are public; evaluator logs/expected values are never forwarded.
            trace = Path(row['path']) / 'control' / 'permissions.jsonl'
            if trace.exists():
                commands = []
                for line in trace.read_text().splitlines():
                    call = json.loads(line).get('toolCall', {})
                    title = str(call.get('title', ''))[:500]
                    if not re.search('token|credential|authorization|bridge.key', title, re.I):
                        commands.append(title)
                entry['public_agent_commands'] = commands[-12:]
            package.append(entry)
        return package

    def model_json(self, prompt, purpose, limit=4):
        import requests
        attempt = purpose + '-' + uuid.uuid4().hex[:12]
        key = secrets.token_urlsafe(32)
        register(self.usage_db, key, attempt, limit)
        try:
            response = requests.post(f"http://127.0.0.1:{self.config['port']}/v1/responses",
                headers={'Authorization': 'Bearer ' + key}, timeout=360,
                json={'model': self.config['model'], 'input': prompt, 'stream': False,
                      'reasoning': {'effort': self.config['thinking']}})
            response.raise_for_status()
            data = response.json()
            if data.get('status') != 'completed':
                raise RuntimeError('Improver response did not complete')
            text = ''.join(c.get('text', '') for item in data.get('output', [])
                           for c in item.get('content', []) if c.get('type') == 'output_text')
            text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip())
            parsed = json.loads(text)
            write(self.root / 'reports' / 'improver' / f'{attempt}.json', {'response_id': data.get('id'),
                  'result': parsed, 'usage': self.usage(attempt)})
            return parsed
        finally:
            self.revoke(attempt)

    def improve(self, strategy, panel, iteration):
        feedback = self.feedback(panel)
        prompt = ('You improve a GENERAL scientific execution strategy. Propose ONE shared failure cause and '
                  'ONE minimal, general instruction to append. Do not include task-specific solutions, '
                  'task IDs in the instruction, benchmark thresholds, target values, hidden information or code. '
                  'Use only the public feedback below. Return JSON with problem, evidence (task_id and attempt_id), '
                  'hypothesis, change (instruction text), expected_effect.\nCurrent strategy:\n'
                  + Path(strategy).read_text() + '\nPublic feedback:\n' + json.dumps(feedback))
        proposal = self.model_json(prompt, f'improve-{iteration}')
        required = {'problem', 'evidence', 'hypothesis', 'change', 'expected_effect'}
        if not required <= proposal.keys() or not isinstance(proposal['change'], str):
            raise ValueError('Invalid strategy proposal')
        if not 1 <= len(proposal['change']) <= 4000:
            raise ValueError('Invalid change size')
        review = self.model_json('Check whether the following strategy addition is a single GENERAL scientific '
            'execution instruction, contains no task-specific answer, hidden target, evaluation threshold or '
            'reference implementation. Return JSON {"allowed": true/false, "reason": "..."}.\n'
            + json.dumps(proposal), f'review-{iteration}')
        directory = self.root / 'strategies' / f'candidate-{iteration}'
        directory.mkdir(parents=True, exist_ok=True)
        write(directory / 'proposal.json', proposal)
        write(directory / 'review.json', review)
        if review.get('allowed') is not True:
            return None
        candidate = directory / 'strategy.md'
        candidate.write_text(Path(strategy).read_text() + '\n\n## Refinement\n' + proposal['change'] + '\n')
        return candidate


def success_counts(panel):
    counts = Counter()
    coverage = defaultdict(set)
    complete = True
    for row in panel:
        if row['repeat'] in coverage[row['task']]:
            complete = False
        coverage[row['task']].add(row['repeat'])
        if row['state'] == 'evaluated' and row['success'] in (0, 1):
            counts[row['task']] += row['success']
        elif row['state'] in ('task_failed', 'budget_exhausted'):
            counts[row['task']] += 0
        else:
            complete = False
    complete = complete and bool(coverage) and all(r == {1,2,3} for r in coverage.values())
    return counts, complete


def decision(current, candidate):
    a, ac = success_counts(current)
    b, bc = success_counts(candidate)
    same = {(r['task'], r['repeat']) for r in current} == {(r['task'], r['repeat']) for r in candidate}
    changed = sorted(t for t in a.keys() | b.keys() if a[t] != b[t])
    regressions = sorted(t for t in a.keys() | b.keys() if b[t] < a[t])
    accept = ac and bc and same and sum(b.values()) > sum(a.values()) and not regressions
    return {'eligible': bool(accept), 'coverage_complete': bool(ac and bc and same),
            'current_successes': sum(a.values()), 'candidate_successes': sum(b.values()),
            'changed_tasks': changed, 'regressions': regressions}


def run_all(runner):
    config, root = runner.config, runner.root
    if not config.get('batch_authorized'):
        raise PermissionError('Batch not authorized')
    protocol_path = root / 'protocol.json'
    protocol = {'config': config, 'config_sha256': runner.config_hash, 'manifest_sha256': sha(root / 'assets/manifest.json'),
                'split': split_tasks(list(runner.tasks.values()), config['development_target'], config['split_seed']),
                'acceptance': 'strict per-task non-regression; three repeats; changed-task confirmation',
                'initial_strategy_sha256': sha(runner.release / 'strategy/initial.md')}
    if protocol_path.exists() and read(protocol_path) != protocol:
        raise ValueError('Frozen protocol differs; start a separate experiment root')
    write(protocol_path, protocol)
    smoke = runner.attempt(0, runner.release / 'strategy/initial.md', 'smoke', 1, smoke=True)
    if smoke['state'] != 'submitted' or not read(Path(smoke['path']) / 'smoke_check.json')['passed']:
        raise RuntimeError('Smoke validation failed')
    initial = runner.release / 'strategy/initial.md'
    # All calibration attempts belong to development. No score-based task selection.
    for repeat in range(1, config['pilot_attempts']+1):
        row = runner.attempt(3, initial, 'pilot', repeat)
        row = runner.evaluate(row['id']) if row['state'] == 'submitted' else row
        if row['state'] != 'evaluated':
            raise RuntimeError('Pilot infrastructure validation failed')
    write(root / 'reports/pilot-validation.json', {'passed': True, 'budget_total': None,
                                                 'batch_authorized_by_user': True})
    dev, holdout = protocol['split']['development'], protocol['split']['holdout']
    current = initial
    panel = runner.panel(dev, current, 'development-initial')
    if not success_counts(panel)[1]:
        raise RuntimeError('Development baseline has technical missingness; evolution paused')
    for iteration in range(1, config['iterations']+1):
        receipt = root / 'reports' / f'iteration-{iteration}.json'
        if receipt.exists():
            previous = read(receipt)
            if previous['accepted']:
                current = Path(previous['candidate'])
                panel = read(root / 'reports' / f'development-candidate-{iteration}.json')
            continue
        candidate = runner.improve(current, panel, iteration)
        if candidate is None:
            write(receipt, {'accepted': False, 'reason': 'candidate_policy_review_rejected'})
            continue
        candidate_panel = runner.panel(dev, candidate, f'development-candidate-{iteration}')
        verdict = decision(panel, candidate_panel)
        if verdict['eligible']:
            a = runner.panel(verdict['changed_tasks'], current, f'confirmation-current-{iteration}')
            b = runner.panel(verdict['changed_tasks'], candidate, f'confirmation-candidate-{iteration}')
            confirmation = decision(a, b)
            verdict['confirmation'] = confirmation
            verdict['eligible'] = confirmation['eligible']
        verdict.update({'accepted': verdict['eligible'], 'candidate': str(candidate),
                        'previous_strategy': str(current), 'iteration': iteration})
        write(receipt, verdict)
        runner.publish_reports()
        if verdict['accepted']:
            current, panel = candidate, candidate_panel
    write(root / 'final-strategy.json', {'path': str(current), 'sha256': sha(current)})
    initial_test = runner.panel(holdout, initial, 'holdout-initial')
    final_test = runner.panel(holdout, current, 'holdout-final')
    report(runner)
    if not success_counts(initial_test)[1] or not success_counts(final_test)[1]:
        raise RuntimeError('Holdout technical missingness; report saved but experiment incomplete')
    write(root / 'completion.json', {'state': 'complete', 'ended': time.time(),
                                     'final_strategy_sha256': sha(current)})
    runner.publish_reports()


def report(runner):
    all_rows = [dict(r) for r in runner.db.execute('SELECT * FROM attempts ORDER BY started')]
    latest = {}
    for row in all_rows:
        latest[row['task'], row['strategy'], row['phase'], row['repeat']] = row
    rows = list(latest.values())
    phases = {}
    for phase in sorted({r['phase'] for r in rows}):
        panel = [r for r in rows if r['phase'] == phase]
        rates = []
        for repeat in sorted({r['repeat'] for r in panel}):
            group = [r for r in panel if r['repeat'] == repeat]
            known = [r for r in group if r['success'] is not None or r['state'] in ('task_failed', 'budget_exhausted')]
            rates.append({'repeat': repeat, 'planned': len(group), 'known': len(known),
                          'successes': sum(r['success'] or 0 for r in known),
                          'success_rate': sum(r['success'] or 0 for r in known)/len(known) if known else None})
        values = [r['success_rate'] for r in rates if r['known'] == r['planned'] and r['success_rate'] is not None]
        phases[phase] = {'rounds': rates, 'mean': statistics.mean(values) if values else None,
                         'sample_sd': statistics.stdev(values) if len(values) > 1 else None,
                         'states': dict(Counter(r['state'] for r in panel)),
                         'complete': all(r['known'] == r['planned'] for r in rates)}
    result = {'phases': phases, 'technical_missingness_preserved': True,
              'primary_metric': 'mean of independent-run success rates; no best-of-three',
              'all_attempt_states': dict(Counter(r['state'] for r in all_rows))}
    split = read(runner.root / 'protocol.json')['split']
    if {'holdout-initial', 'holdout-final'} <= phases.keys() and all(phases[p]['complete'] for p in ('holdout-initial', 'holdout-final')):
        a = {(r['task'], r['repeat']): r['success'] or 0 for r in rows if r['phase'] == 'holdout-initial'}
        b = {(r['task'], r['repeat']): r['success'] or 0 for r in rows if r['phase'] == 'holdout-final'}
        if a.keys() == b.keys():
            groups = [[i for i in g if i in split['holdout']] for g in split['groups']]
            groups = [g for g in groups if g]
            rng = random.Random(20261009)
            samples = []
            for _ in range(10000):
                selected = [i for g in rng.choices(groups, k=len(groups)) for i in g]
                samples.append(statistics.mean(b[i,r]-a[i,r] for i in selected for r in (1,2,3)))
            samples.sort()
            result['paired_holdout'] = {'delta': statistics.mean(b[k]-a[k] for k in a),
                'group_bootstrap_95_ci': [samples[249], samples[9749]],
                'regressed_tasks': sorted(i for i in split['holdout'] if sum(b[i,r] for r in (1,2,3)) < sum(a[i,r] for r in (1,2,3)))}
    with connect(runner.usage_db) as db:
        usage = [json.loads(r[0]) for r in db.execute('SELECT usage FROM requests WHERE usage IS NOT NULL')]
        result['model_requests'] = db.execute('SELECT COUNT(*) FROM requests').fetchone()[0]
        result['missing_usage'] = db.execute('SELECT COUNT(*) FROM requests WHERE usage IS NULL').fetchone()[0]
    result['tokens'] = {k: sum(u.get(k,0) for u in usage) for k in ('input_tokens','output_tokens','total_tokens')}
    result['actual_dollar_cost'] = None
    write(runner.root / 'reports/summary.json', result)
    runner.publish_reports()
    print(json.dumps(result, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('command', choices=['smoke', 'run', 'evaluate', 'improve', 'evolve', 'all', 'report', 'status'])
    parser.add_argument('--task', type=int, default=3)
    parser.add_argument('--strategy')
    parser.add_argument('--attempt')
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--phase', default='manual')
    args = parser.parse_args()
    release = Path(__file__).resolve().parent.parent
    runner = Runner(read(args.config), release)
    strategy = args.strategy or str(release / 'strategy/initial.md')
    if args.command == 'smoke':
        print(runner.attempt(0, strategy, 'smoke', 1, True))
    elif args.command == 'run':
        print(runner.attempt(args.task, strategy, args.phase, args.repeat))
    elif args.command == 'evaluate':
        print(runner.evaluate(args.attempt))
    elif args.command == 'improve':
        print(runner.improve(strategy, read(runner.root / 'reports' / f'{args.phase}.json'), args.repeat))
    elif args.command in ('all', 'evolve'):
        run_all(runner)
    elif args.command == 'report':
        report(runner)
    else:
        print(json.dumps({'states': dict(runner.db.execute('SELECT state,COUNT(*) FROM attempts GROUP BY state').fetchall()),
            'latest': [dict(r) for r in runner.db.execute('SELECT * FROM attempts ORDER BY started DESC LIMIT 3')]}, indent=2))


if __name__ == '__main__':
    main()
