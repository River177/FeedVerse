"""Run web regression tests using an installed FeedVerse Python environment."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
candidates = [os.getenv('FEEDVERSE_PYTHON'), str(ROOT / '.venv/bin/python'),
              str(Path.home() / 'miniforge3/bin/python3.13'), sys.executable]
for candidate in candidates:
    if not candidate or not Path(candidate).exists():
        continue
    probe = subprocess.run([candidate, '-c', 'import torch, fastapi, httpx, numpy'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if probe.returncode == 0:
        raise SystemExit(subprocess.run([candidate, '-m', 'unittest', 'discover',
                                        '-s', 'tests/web', '-v'], cwd=ROOT).returncode)
raise SystemExit('Install requirements-core.txt and requirements-web.txt; set FEEDVERSE_PYTHON to that interpreter.')
