#!/usr/bin/env bash
set -euo pipefail
FEEDVERSE_PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
FEEDVERSE_AGH="$FEEDVERSE_PROJECT/local/agh-pinned"
FEEDVERSE_COMMIT=a39272bb6bcb3109584e1bd3abac595789ae365d
mkdir -p "$FEEDVERSE_PROJECT/local"
if [ ! -f "$FEEDVERSE_AGH/package.json" ]; then
  curl --fail --location --retry 2 "https://codeload.github.com/AgnesAI-Labs/agnes-harness/tar.gz/$FEEDVERSE_COMMIT" -o "$FEEDVERSE_PROJECT/local/agh-source.tar.gz"
  mkdir -p "$FEEDVERSE_AGH"
  tar -xzf "$FEEDVERSE_PROJECT/local/agh-source.tar.gz" -C "$FEEDVERSE_AGH" --strip-components=1
fi
cd "$FEEDVERSE_AGH"
# npm_config_registry / HTTPS_PROXY can follow the machine's existing network setup.
FEEDVERSE_PNPM_VERSION="$(npm exec --yes --package=pnpm@10.34.5 -- pnpm --version)"
[ "$FEEDVERSE_PNPM_VERSION" = '10.34.5' ] || { echo 'Wrong pnpm version' >&2; exit 1; }
npm exec --yes --package=pnpm@10.34.5 -- pnpm install --frozen-lockfile
npm exec --yes --package=pnpm@10.34.5 -- pnpm --filter @agnes/cli build:local
node packages/cli/dist/local/agnes.mjs --help
