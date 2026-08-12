#!/usr/bin/env bash
set -Eeuo pipefail

# Provision the one Python environment used by the Discovery sidecar and its
# production worker.  The three requirement files are resolved together so
# DR/PaperOrchestra cannot silently leave a later import missing.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM="$ROOT/desktop/openworker/upstream"
RUNTIME_VENV="${VEGAPUNK_VENV:-$UPSTREAM/.venv311}"
RUNTIME_CONSTRAINTS="$ROOT/config/runtime_constraints.txt"

if [[ ! -x "$RUNTIME_VENV/bin/python" ]]; then
  if command -v uv >/dev/null 2>&1; then
    uv venv --python 3.11 "$RUNTIME_VENV"
  elif command -v python3.11 >/dev/null 2>&1; then
    python3.11 -m venv "$RUNTIME_VENV"
  else
    echo "runtime: Python 3.11 or uv is required" >&2
    exit 1
  fi
fi

if command -v uv >/dev/null 2>&1; then
  uv pip install --python "$RUNTIME_VENV/bin/python" \
    -c "$RUNTIME_CONSTRAINTS" \
    -r "$ROOT/requirements.txt" \
    -r "$ROOT/vegapunk/mas/agents/dr_agents/requirements.txt" \
    -r "$ROOT/third_party/paper_orchestra/requirements.txt" \
    -e "$UPSTREAM[dev,messaging,browser,bedrock]"
else
  "$RUNTIME_VENV/bin/python" -m pip install --upgrade pip
  "$RUNTIME_VENV/bin/python" -m pip install \
    -c "$RUNTIME_CONSTRAINTS" \
    -r "$ROOT/requirements.txt" \
    -r "$ROOT/vegapunk/mas/agents/dr_agents/requirements.txt" \
    -r "$ROOT/third_party/paper_orchestra/requirements.txt" \
    -e "$UPSTREAM[dev,messaging,browser,bedrock]"
fi

"$RUNTIME_VENV/bin/python" -m pip check
echo "runtime: ready at $RUNTIME_VENV"
