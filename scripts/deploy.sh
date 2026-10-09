#!/usr/bin/env bash
set -euo pipefail
repo_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$repo_root"
if [[ -n $(git status --porcelain) ]]; then
  echo 'Commit changes before deployment.' >&2
  exit 1
fi
revision=$(git rev-parse HEAD)
remote_root=/datadisk/agh-rsi
release="$remote_root/releases/$revision"
ssh -o BatchMode=yes gcr-a100 "mkdir -p '$release'"
git archive "$revision" | ssh -o BatchMode=yes gcr-a100 "tar -x -C '$release'"
python3 - "$revision" <<'PY' | ssh -o BatchMode=yes gcr-a100 "cat > '$release/DEPLOYMENT.json'"
import json,sys
print(json.dumps({'git_commit':sys.argv[1],'repository':'https://github.com/River177/AGH-RSI'}))
PY
echo "$release"
