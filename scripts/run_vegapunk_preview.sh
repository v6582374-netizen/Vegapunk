#!/usr/bin/env bash
set -Eeuo pipefail

# Start the browser preview as one managed unit.  The Web Sidecar is the API and
# WebSocket server; Vite is only the browser frontend and must not be considered
# ready until the Sidecar is healthy.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM="$ROOT/desktop/openworker/upstream"
GUI_DIR="$UPSTREAM/surfaces/gui"
SIDECAR_BIN="$UPSTREAM/.venv/bin/openworker-server"
GUI_DIST="$GUI_DIR/dist"
SIDECAR_URL="http://127.0.0.1:8765"
PREVIEW_URL="http://127.0.0.1:1420"

sidecar_pid=""
vite_pid=""

cleanup() {
  local status=$?
  trap - EXIT INT TERM

  if [[ -n "$vite_pid" ]] && kill -0 "$vite_pid" 2>/dev/null; then
    kill "$vite_pid" 2>/dev/null || true
  fi
  if [[ -n "$sidecar_pid" ]] && kill -0 "$sidecar_pid" 2>/dev/null; then
    kill "$sidecar_pid" 2>/dev/null || true
  fi

  wait 2>/dev/null || true
  exit "$status"
}

trap cleanup EXIT
trap 'exit 143' INT TERM

if [[ ! -x "$SIDECAR_BIN" ]]; then
  echo "preview: missing Sidecar executable: $SIDECAR_BIN" >&2
  exit 1
fi

if [[ ! -d "$GUI_DIR" ]]; then
  echo "preview: missing GUI directory: $GUI_DIR" >&2
  exit 1
fi

sidecar_ready() {
  curl -fsS --max-time 2 "$SIDECAR_URL/v1/health" >/dev/null 2>&1 &&\
    curl -fsS --max-time 2 "$SIDECAR_URL/v1/discovery" >/dev/null 2>&1
}

wait_for_sidecar() {
  local deadline=$((SECONDS + 30))
  while (( SECONDS < deadline )); do
    if sidecar_ready; then
      return 0
    fi
    if [[ -n "$sidecar_pid" ]] && ! kill -0 "$sidecar_pid" 2>/dev/null; then
      wait "$sidecar_pid" || true
      return 1
    fi
    sleep 0.25
  done
  return 1
}

wait_for_preview() {
  local deadline=$((SECONDS + 30))
  while (( SECONDS < deadline )); do
    if curl -fsS --max-time 2 "$PREVIEW_URL/" >/dev/null 2>&1; then
      return 0
    fi
    if ! kill -0 "$vite_pid" 2>/dev/null; then
      wait "$vite_pid" || true
      return 1
    fi
    sleep 0.25
  done
  return 1
}

if ! sidecar_ready; then
  echo "preview: starting Web Sidecar on 127.0.0.1:8765"
  "$SIDECAR_BIN" \
    --web \
    --web-dist "$GUI_DIST" \
    --host 127.0.0.1 \
    --port 8765 \
    --cwd "$ROOT" &
  sidecar_pid=$!
else
  echo "preview: reusing healthy Web Sidecar on 127.0.0.1:8765"
fi

if ! wait_for_sidecar; then
  echo "preview: Web Sidecar did not become healthy" >&2
  exit 1
fi
echo "preview: Web Sidecar is healthy"

echo "preview: starting Vite on 0.0.0.0:1420"
(
  cd "$GUI_DIR"
  exec npm run dev -- --host 0.0.0.0
) &
vite_pid=$!

if ! wait_for_preview; then
  echo "preview: Vite did not become reachable" >&2
  exit 1
fi
echo "preview: Vite is reachable at $PREVIEW_URL"

if [[ -n "$sidecar_pid" ]]; then
  wait -n "$sidecar_pid" "$vite_pid"
else
  wait "$vite_pid"
fi
