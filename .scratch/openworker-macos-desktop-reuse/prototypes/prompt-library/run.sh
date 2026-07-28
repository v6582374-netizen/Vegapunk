#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PORT="${PORT:-4174}"

printf 'OpenWorker Prompt Library prototype\n'
printf '  http://127.0.0.1:%s/?variant=A\n' "$PORT"
printf '  variants: A, B, C\n'
printf '  stop: Ctrl-C\n\n'

python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$ROOT"
