# OpenWorker Desktop App (React + Tauri)

A thin client of the coworker server (OpenAI-compatible API + WS event/approval stream).
The supported product surface is the native OpenWorker Desktop App; the browser Vite mode below is retained only as a development/test harness for the same GUI source.

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

## Browser harness (development only)

The GUI source can still run in a browser for hermetic UI development and tests. This is not a second product frontend:

```bash
cd desktop/openworker/upstream
.venv/bin/openworker-server --cwd /path/to/your/project --port 8765

cd surfaces/gui
npm run dev            # → http://localhost:5173
```

Open `http://localhost:5173` only when working on the GUI harness. The UI talks to `http://127.0.0.1:8765` (override with `VITE_COWORKER_HTTP` / `VITE_COWORKER_WS`).

## Prompt Library backend

Desktop Settings → Prompt Library uses the same authenticated `openworker-server` sidecar as Discovery and the rest of the Native Desktop application.

The sidecar exposes `/v1/prompt-library/*` for active Prompt Library bodies and `/v1/discovery/input-conversion-prompt` for the editable Discovery Input Conversion Prompt.

The sidecar is the single local service boundary; no second API process or fixed port is required.

## Tests

```bash
npx tsc --noEmit && npx vitest run   # GUI typecheck + unit
npx playwright test                  # hermetic e2e (mocked /v1 + WS, no Python needed)
```
