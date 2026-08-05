# OpenWorker Desktop App and Linux Web Counterpart (React + Tauri)

A thin client of the coworker server (OpenAI-compatible API + WS event/approval stream).
The macOS Desktop App and Linux Web Counterpart intentionally use the same React bundle; the
browser deployment is not a redesigned or reduced admin console.

## First time: bootstrap the Python backend

A fresh checkout has no server to run — create the venv both flows below expect:

```bash
cd desktop/openworker/upstream
bash packaging/setup_dev_env.sh   # → .venv (server + this repo's aisuite)
```

## Run the Desktop App from source

The Tauri shell is the supported product entry point. It wraps the React UI and supervises the Python server itself — no separate server terminal is needed:

```bash
cd desktop/openworker/upstream/surfaces/gui
npm ci                 # first time
npm run tauri dev      # builds the shell, launches the window, starts the server
```

The development shell finds the server at `desktop/openworker/upstream/.venv/bin/openworker-server` automatically. A packaged sidecar binary is produced only by the release scripts in `desktop/openworker/upstream/packaging/`.

## Linux Web Counterpart

Build the exact desktop GUI bundle once, then let the Python server serve it as a same-origin SPA.
The same-origin session cookie keeps the API token out of browser JavaScript while REST and WS
routes remain under the existing `/v1` and `/ws` contract.

```bash
cd desktop/openworker/upstream/surfaces/gui
npm ci
npm run build

cd ../..
export COWORKER_WEB_TOKEN="replace-with-a-long-random-token"
.venv/bin/openworker-server \
  --web \
  --web-dist surfaces/gui/dist \
  --host 0.0.0.0 \
  --port 8765 \
  --cwd /srv/openworker/workspace
```

Open `http://<linux-host>:8765/`, enter `COWORKER_WEB_TOKEN`, and the desktop surface loads
unchanged. Put TLS and any organization SSO in front of the process for shared deployments.
`COWORKER_WEB_TOKEN` is intentionally required for a network-facing server; omitting it leaves
Web authentication disabled for trusted/private-network development only.

The web build has explicit platform capability exceptions: native macOS window controls,
autostart/keep-awake, the local Tauri updater, and local dictation remain desktop-only. Folder
selection uses the server-side Linux picker endpoint, and external links use the browser.

## Browser harness (development)

The GUI source can still run in a browser for hermetic UI development and tests. This is not a second product frontend:

```bash
cd desktop/openworker/upstream
.venv/bin/openworker-server --cwd /path/to/your/project --port 8765

cd surfaces/gui
npm run dev            # → http://localhost:1420
```

Open `http://localhost:1420` when working on the GUI harness. Browser development uses Vite's
same-origin `/v1` and `/ws` proxy to reach `http://127.0.0.1:8765`, so the UI also works when
opened from another device via `npm run dev -- --host 0.0.0.0`. Override the sidecar target with
`VITE_COWORKER_HTTP` (and `VITE_COWORKER_WS` for a direct WebSocket). The harness does not
enable the server-hosted same-origin marker; production Web deployments use
`openworker-server --web` above.

## Prompt Library backend

Desktop Settings → Prompt Library uses the same authenticated `openworker-server` sidecar as Discovery and the rest of the Native Desktop application.

The sidecar exposes `/v1/prompt-library/*` for active Prompt Library bodies and `/v1/discovery/input-conversion-prompt` for the editable Discovery Input Conversion Prompt.

The sidecar is the single local service boundary; no second API process or fixed port is required.

## Tests

```bash
npx tsc --noEmit && npx vitest run   # GUI typecheck + unit
npx playwright test                  # hermetic e2e (mocked /v1 + WS, no Python needed)
```
