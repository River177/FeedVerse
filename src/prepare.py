"""Fetch pinned official inputs on the experiment host, never into Git."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request
import zipfile
import requests

ARCHIVE_URL = ('https://buckeyemailosu-my.sharepoint.com/:u:/g/personal/chen_8336_osu_edu/'
               'IQB870QrmuqwS5Ck33cHpJfkAVt3LsMeariREIwP3AT7byA?download=1')


def download(url, target):
    if target.exists():
        return
    temp = target.with_suffix(target.suffix + '.partial')
    print('Downloading', target.name, flush=True)
    with requests.Session() as session:
        with session.get(url, stream=True, timeout=(30, 120)) as response, temp.open('wb') as out:
            response.raise_for_status()
            for chunk in response.iter_content(1024*1024):
                out.write(chunk)
    temp.replace(target)


def hashfile(path):
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def prepare(config, build=True):
    root = Path(config['root'])
    assets = root / 'assets'
    assets.mkdir(parents=True, exist_ok=True)
    repo = assets / 'ScienceAgentBench'
    if not repo.exists():
        subprocess.run(['git', 'clone', 'https://github.com/OSU-NLP-Group/ScienceAgentBench', str(repo)], check=True)
    subprocess.run(['git', '-C', str(repo), 'checkout', '--detach', config['benchmark_commit']], check=True)
    annotations = assets / 'verified.parquet'
    download(f"https://huggingface.co/datasets/osunlp/ScienceAgentBench/resolve/{config['dataset_revision']}/data/verified-00000-of-00001.parquet", annotations)
    import pyarrow.parquet as pq
    rows = pq.read_table(annotations).to_pylist()
    if len(rows) != 102 or len({r['instance_id'] for r in rows}) != 102:
        raise ValueError('Expected 102 unique verified tasks')
    (assets / 'tasks.json').write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    archive = assets / 'benchmark_verified.zip'
    download(ARCHIVE_URL, archive)
    extracted = assets / 'verified'
    if not (extracted / '.extracted').exists():
        extracted.mkdir(exist_ok=True)
        with zipfile.ZipFile(archive) as z:
            for member in z.infolist():
                if Path(member.filename).is_absolute() or '..' in Path(member.filename).parts:
                    raise ValueError('Unsafe archive path')
            z.extractall(extracted, pwd=b'scienceagentbench')
        (extracted / '.extracted').write_text(hashfile(archive))
    candidates = list(extracted.rglob('eval_programs'))
    if len(candidates) != 1:
        raise ValueError('Could not uniquely identify verified benchmark root')
    benchmark = candidates[0].parent
    files = {str(p.relative_to(benchmark)): hashfile(p)
             for p in sorted(benchmark.rglob('*')) if p.is_file()}
    manifest = {'benchmark_commit': config['benchmark_commit'], 'dataset_revision': config['dataset_revision'],
                'annotations_sha256': hashfile(annotations), 'archive_sha256': hashfile(archive),
                'benchmark_path': str(benchmark), 'files': files}
    (assets / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    # Keep upstream evaluator functions unchanged. Use its exact base Dockerfile.
    spec = importlib.util.spec_from_file_location('dockerfiles', repo / 'evaluation/harness/dockerfiles.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dockerfile = module.get_dockerfile_base('linux/amd64', 'x86_64')
    # Avoid defaults-channel ToS prompts in unattended builds; package bounds remain upstream's.
    dockerfile = dockerfile.replace('conda config --append channels conda-forge',
                                   'conda config --remove channels defaults && conda config --add channels conda-forge')
    context = root / 'control' / 'image'
    context.mkdir(parents=True, exist_ok=True)
    (context / 'Dockerfile').write_text(dockerfile)
    if build:
        subprocess.run(['docker', 'build', '--platform', 'linux/amd64', '-t', config['image'], str(context)], check=True)
        image = subprocess.check_output(['docker', 'image', 'inspect', config['image'], '--format', '{{.Id}}'], text=True).strip()
        manifest.update({'image_id': image, 'dockerfile_sha256': hashfile(context / 'Dockerfile'),
                         'environment_patch': 'conda-forge-only channels; upstream package constraints unchanged'})
        (assets / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({'task_count': len(rows), 'benchmark_path': str(benchmark),
                      'archive_sha256': manifest['archive_sha256']}, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--no-build', action='store_true')
    args = parser.parse_args()
    prepare(json.loads(Path(args.config).read_text()), not args.no_build)
