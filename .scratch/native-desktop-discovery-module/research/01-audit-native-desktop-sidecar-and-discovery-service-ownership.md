# Native Desktop Sidecar and Discovery Service Ownership

## Scope

This audit answers which current native desktop process, API, authentication, and storage conventions can host Discovery without starting a second user-visible service.

The evidence is limited to the current checkout, with no product code changes made.

## Executive finding

The native Desktop App already owns one long-lived Python FastAPI sidecar, and Discovery should become a namespaced capability of that sidecar rather than a second FastAPI process.

The independent Discovery Sidebar decision is therefore a UI navigation decision, not a process ownership decision.

The existing Discovery domain seams are reusable, but the current `admin_console.app:create_app` factory is not a drop-in native backend because it assumes repository-root storage, its own provider connection service, unauthenticated `/api/*` routes, and a separate port.

## Native desktop process and API conventions

### Tauri starts exactly one managed sidecar

`desktop/openworker/upstream/surfaces/gui/src-tauri/src/lib.rs` chooses a free loopback port, creates an in-memory launch token, and injects the HTTP URL, WebSocket URL, and token into the WebView before the SPA loads.

[Source: `desktop/openworker/upstream/surfaces/gui/src-tauri/src/lib.rs:566-576`](../../../desktop/openworker/upstream/surfaces/gui/src-tauri/src/lib.rs:566-576).

The setup hook resolves one `openworker-server` binary, passes the chosen port, enables parent-liveness cleanup, passes the token through `COWORKER_API_TOKEN`, and stores the child in `ServerProcess`.

[Source: `desktop/openworker/upstream/surfaces/gui/src-tauri/src/lib.rs:687-734`](../../../desktop/openworker/upstream/surfaces/gui/src-tauri/src/lib.rs:687-734).

The same setup hook redirects sidecar stdout and stderr to `<state_dir>/logs/openworker-server.log`, retaining the previous file as `.old`.

[Source: `desktop/openworker/upstream/surfaces/gui/src-tauri/src/lib.rs:137-148`](../../../desktop/openworker/upstream/surfaces/gui/src-tauri/src/lib.rs:137-148).

Closing the window hides it to the tray and keeps the sidecar alive, while a true application exit kills the managed sidecar child.

[Source: `desktop/openworker/upstream/surfaces/gui/src-tauri/src/lib.rs:773-780`](../../../desktop/openworker/upstream/surfaces/gui/src-tauri/src/lib.rs:773-780).

[Source: `desktop/openworker/upstream/surfaces/gui/src-tauri/src/lib.rs:815-828`](../../../desktop/openworker/upstream/surfaces/gui/src-tauri/src/lib.rs:815-828).

### The Python entrypoint is already designed as a sidecar

The Python launcher constructs `SessionManager` with `state_dir()` as its data directory and then passes that manager to `coworker.server.app.create_app`.

[Source: `desktop/openworker/upstream/coworker/server/run.py:102-109`](../../../desktop/openworker/upstream/coworker/server/run.py:102-109).

The launcher publishes the actual selected port, preserves a Tauri-supplied token in memory, watches the Tauri parent process, and runs the FastAPI app with Uvicorn.

[Source: `desktop/openworker/upstream/coworker/server/run.py:128-171`](../../../desktop/openworker/upstream/coworker/server/run.py:128-171).

The sidecar exits when its explicit parent PID dies, which is important because the packaged Python process can be a grandchild of the Tauri process.

[Source: `desktop/openworker/upstream/coworker/server/run.py:18-64`](../../../desktop/openworker/upstream/coworker/server/run.py:18-64).

### Native storage and credentials have one existing root

Both Rust and Python resolve the native state root from `COWORKER_STATE_DIR`, then Windows `%APPDATA%/coworker`, or POSIX `~/.config/coworker`.

[Source: `desktop/openworker/upstream/surfaces/gui/src-tauri/src/lib.rs:117-131`](../../../desktop/openworker/upstream/surfaces/gui/src-tauri/src/lib.rs:117-131).

[Source: `desktop/openworker/upstream/coworker/secrets.py:27-43`](../../../desktop/openworker/upstream/coworker/secrets.py:27-43).

`SessionManager` stores conversations, memory, audit data, UI preferences, and its `SecretStore` under the selected native data directory.

[Source: `desktop/openworker/upstream/coworker/server/manager.py:108-166`](../../../desktop/openworker/upstream/coworker/server/manager.py:108-166).

The native provider router reads provider profiles from this same `SecretStore`, and the native settings surface exposes the active model and configured model set through the manager.

[Source: `desktop/openworker/upstream/coworker/server/manager.py:1390-1419`](../../../desktop/openworker/upstream/coworker/server/manager.py:1390-1419).

[Source: `desktop/openworker/upstream/coworker/server/manager.py:1738-1784`](../../../desktop/openworker/upstream/coworker/server/manager.py:1738-1784).

### Native REST and WebSocket calls already have a single transport wrapper

The GUI resolves the sidecar URL from Tauri-injected globals, then falls back to Vite environment variables or the browser development port.

[Source: `desktop/openworker/upstream/surfaces/gui/src/api.ts:5-19`](../../../desktop/openworker/upstream/surfaces/gui/src/api.ts:5-19).

Every native REST call adds `X-OpenWorker-Token`, and every authenticated WebSocket uses the `openworker` subprotocol plus the same token.

[Source: `desktop/openworker/upstream/surfaces/gui/src/api.ts:21-37`](../../../desktop/openworker/upstream/surfaces/gui/src/api.ts:21-37).

The Python FastAPI app enforces this token on all non-tokenless HTTP paths and on WebSockets, while allowing only health and OAuth callback paths to bypass the token.

[Source: `desktop/openworker/upstream/coworker/server/app.py:165-231`](../../../desktop/openworker/upstream/coworker/server/app.py:165-231).

New Discovery endpoints should therefore use the native `/v1` namespace and inherit this middleware instead of exposing a second unauthenticated `/api` surface.

## Current Web-side Discovery ownership

### `admin_console` is still a separate service boundary

The Admin Console README states that the module provides Discovery and artifact APIs, no longer hosts the product Web frontend, and is currently started as a separate Uvicorn service on port 8000.

[Source: `admin_console/README.md:1-11`](../../../admin_console/README.md:1-11).

The README lists `/api/admin/*`, `/api/workspace/*`, and `/api/prompt-library/v1` as the service routes, then explicitly says that moving Prompt Library into the Desktop sidecar is future work.

[Source: `admin_console/README.md:13-19`](../../../admin_console/README.md:13-19).

The README also states that the local API does not use authentication and relies on the launcher to control its exposure boundary.

[Source: `admin_console/README.md:21-21`](../../../admin_console/README.md:21-21).

This is incompatible with the native sidecar's token boundary if the two applications remain separate.

### The Admin Console factory hardcodes a repository-oriented composition

`admin_console.app.create_app` defaults to `<repository>/results`, `<repository>/tasks`, and the repository configuration files.

[Source: `admin_console/app.py:221-249`](../../../admin_console/app.py:221-249).

The factory constructs `ProviderConnectionService`, `DefaultDiscoveryInputConverter`, `LaunchQueue`, and `DiscoveryPreparationStore` as one Web service composition.

[Source: `admin_console/app.py:251-298`](../../../admin_console/app.py:251-298).

The factory applies `TrustedHostMiddleware` and a same-origin middleware designed for `/api` requests rather than the native sidecar token middleware.

[Source: `admin_console/app.py:300-348`](../../../admin_console/app.py:300-348).

The current `/api/workspace` routes expose preparation, conversion, revision, launch, status, SSE log, and artifact operations directly from that factory.

[Source: `admin_console/app.py:350-667`](../../../admin_console/app.py:350-667).

The current `/api/admin` routes expose the broader task, queue, model, provider, prompt, artifact, timeline, stop, kill, and resume operations.

[Source: `admin_console/app.py:717-1133`](../../../admin_console/app.py:717-1133).

The route handlers are useful evidence of the product contract, but the factory itself should not become the native process entrypoint.

## Reusable Discovery domain seams

### Preparation storage and file validation

`DiscoveryPreparationStore` durably stores one preparation under a results-root subdirectory, preserves research text and source metadata, and stores uploaded bytes under a private `sources` directory.

[Source: `admin_console/preparations.py:29-89`](../../../admin_console/preparations.py:29-89).

The current source whitelist is `.txt`, `.md`, `.pdf`, `.docx`, `.csv`, and `.zip`, with `.zip` classified as baseline code.

[Source: `admin_console/preparations.py:11-18`](../../../admin_console/preparations.py:11-18).

The store rejects path-like upload names, rejects unsupported extensions, and re-reads saved bytes at conversion and launch boundaries.

[Source: `admin_console/preparations.py:99-108`](../../../admin_console/preparations.py:99-108).

[Source: `admin_console/preparations.py:160-178`](../../../admin_console/preparations.py:160-178).

The store supports explicit editable Formatted Discovery Input revisions and raw research-text updates without rewriting prior revisions.

[Source: `admin_console/preparations.py:110-150`](../../../admin_console/preparations.py:110-150).

This is reusable in the sidecar after replacing the repository-relative root with an explicit native Discovery data root.

### Input conversion

`DefaultDiscoveryInputConverter` resolves the configured active text model, resolves provider credentials, extracts text from supported source types, and returns an editable formatted input plus the model identifier.

[Source: `admin_console/discovery_conversion.py:62-146`](../../../admin_console/discovery_conversion.py:62-146).

The converter uses the Admin Console's `model_catalog.yaml` and `ProviderConnectionService`, so its conversion algorithm is reusable but its credential and model adapter must be connected to the native `SessionManager` configuration.

[Source: `admin_console/discovery_conversion.py:73-113`](../../../admin_console/discovery_conversion.py:73-113).

The source extraction helper already handles UTF-8 text, PDF, DOCX, CSV, and ZIP package validation, including traversal checks for ZIP members.

[Source: `admin_console/discovery_conversion.py:149-194`](../../../admin_console/discovery_conversion.py:149-194).

### Serial queue and launch snapshots

`LaunchQueue` is explicitly a service-wide serial execution seam, persists queue entries under `results_root/launch_queue.json`, and refuses a second queued or running Launch.

[Source: `admin_console/queue.py:1-8`](../../../admin_console/queue.py:1-8).

[Source: `admin_console/queue.py:67-119`](../../../admin_console/queue.py:67-119).

The queue allocates a launch directory, captures configuration and prompt snapshots before execution, and passes the snapshot-derived runtime configuration to the child process.

[Source: `admin_console/queue.py:153-169`](../../../admin_console/queue.py:153-169).

[Source: `admin_console/queue.py:236-264`](../../../admin_console/queue.py:236-264).

The queue writes the merged child output to `runner.log`, starts the runner in a new process group, and records completed, failed, or aborted outcomes.

[Source: `admin_console/queue.py:284-331`](../../../admin_console/queue.py:284-331).

Graceful and forced stop are already represented as process-group signals, and a resumed Launch keeps its original snapshot.

[Source: `admin_console/queue.py:92-142`](../../../admin_console/queue.py:92-142).

[Source: `admin_console/queue.py:246-264`](../../../admin_console/queue.py:246-264).

These are the correct runtime primitives for the confirmed V1 rule of one active Launch, Stop, and Resume.

### Launch history, status, logs, and artifacts

`launches.py` scans persisted launch directories and derives terminal states from durable outcome or checkpoint artifacts.

[Source: `admin_console/launches.py:1-79`](../../../admin_console/launches.py:1-79).

`live.py` derives stage and round counts from on-disk Discovery artifacts, lists recent files, and streams appended `runner.log` lines over SSE without requiring a WebSocket or filesystem watcher.

[Source: `admin_console/live.py:1-92`](../../../admin_console/live.py:1-92).

`artifacts.py` confines artifact resolution to the launch directory and exposes a recursive tree and MIME-aware file response.

[Source: `admin_console/artifacts.py:1-68`](../../../admin_console/artifacts.py:1-68).

`discovery_workspace.py` provides the researcher-facing artifact filter that hides machine-only files while reusing the path-confined resolver.

[Source: `admin_console/discovery_workspace.py:1-89`](../../../admin_console/discovery_workspace.py:1-89).

These helpers are transport-neutral and can back the native Discovery UI after the route layer is moved under `/v1/discovery`.

## Integration boundary

### Recommended ownership

The Tauri-managed `openworker-server` sidecar should be the only user-visible local service for the Desktop App.

The sidecar's existing `coworker.server.app.create_app` should mount a Discovery service facade or router under `/v1/discovery/...`.

The facade should own one configured `DiscoveryPreparationStore`, one `LaunchQueue`, one conversion service, and the launch history, live status, log, and artifact helpers for the sidecar lifetime.

The native sidecar should keep Discovery data under an explicit user-owned root derived from `SessionManager`'s `state_dir` or `_data_base`, rather than the repository's `results` and `tasks` directories.

The exact subdirectory name can be decided by the dependent persistence ticket, but it must be stable across Desktop App restarts and independent of the currently selected conversation workspace.

The Discovery facade should receive an adapter for the native model and credential services so conversion and execution use the global Desktop settings already exposed by `SessionManager`.

The native UI should call the same `api.ts` transport wrapper, which automatically targets the injected sidecar port and supplies the sidecar token.

An independent Discovery Sidebar module can therefore remain fully separate from New Session state while using the same authenticated sidecar process.

### Code to reuse

- Reuse `admin_console.preparations.DiscoveryPreparationStore` after making its root explicit and native-state-backed.
- Reuse `admin_console.discovery_conversion` source parsing, conversion request types, result types, and error taxonomy after adapting model and credential resolution.
- Reuse `admin_console.queue.LaunchQueue` and its serial admission, snapshot, stop, resume, log, and persistence behavior after making roots and runner command explicit.
- Reuse `admin_console.launches`, `admin_console.live`, `admin_console.artifacts`, and `admin_console.discovery_workspace` as transport-neutral persisted-run views.
- Reuse the current `launch_discovery.py` runner contract only through a packaged or configured command that is valid in the Desktop installation.
- Reuse the current native `SessionManager` data root, `SecretStore`, provider router, model settings, sidecar token middleware, and `api.ts` transport wrapper.

### Web-only or migration-only code

- Treat `admin_console.app.create_app` as a Web service composition and test harness, not as the native production process entrypoint.
- Treat `/api/workspace/*` and `/api/admin/*` as current Web route shapes that must be replaced or adapted to `/v1/discovery/*` for the Desktop App.
- Treat `TrustedHostMiddleware` and the `same_origin_api_requests` middleware as Web-service assumptions, because native calls already have token authentication in the sidecar.
- Treat the separate Uvicorn port 8000 and the README's no-auth exposure model as migration-only development infrastructure.
- Treat the repository-root defaults for `results`, `tasks`, config files, prompt library, and provider connections as Web or checkout assumptions that cannot define native Desktop storage.
- Treat the Admin Console's `ProviderConnectionService` wiring as an adapter candidate, not a second credential store alongside the native `SessionManager.secrets`.
- Treat the separate `/api/prompt-library/v1` service as an existing cross-service dependency that should not be copied into Discovery's runtime boundary without an explicit migration decision.

## Lifecycle caveat requiring a follow-up decision

The native shell kills the direct sidecar child on application exit, while `LaunchQueue` starts Discovery runners in a new process group and persists their PID and queue state.

[Source: `desktop/openworker/upstream/surfaces/gui/src-tauri/src/lib.rs:815-823`](../../../desktop/openworker/upstream/surfaces/gui/src-tauri/src/lib.rs:815-823).

[Source: `admin_console/queue.py:284-320`](../../../admin_console/queue.py:284-320).

This means the integration must explicitly decide whether application quit gracefully stops the active Launch, leaves it for a new sidecar to adopt, or marks it interrupted for Resume.

The queue already supports adopted-run observation and marks a dead running process as interrupted after restart, but the Desktop shutdown path does not currently call the queue's stop API before killing the sidecar.

[Source: `admin_console/queue.py:209-222`](../../../admin_console/queue.py:209-222).

[Source: `admin_console/queue.py:339-350`](../../../admin_console/queue.py:339-350).

This is a lifecycle contract to resolve in the single-active-launch and Desktop transport tickets, not a reason to introduce a second service.

## Recommendation

Adopt one authenticated native sidecar with a native `/v1/discovery` router and a Discovery service facade configured from the sidecar's user data root and native settings.

Keep the Discovery Sidebar independent in the React navigation, but do not spawn a separate `admin_console` process for it.

Retain `admin_console` as a compatibility and test surface until the native router has parity, then remove the Desktop dependency on port 8000 and the unauthenticated `/api` routes.

The next design tickets should decide the exact native data-root layout, the model and secret adapter, the launch shutdown and Resume contract, the route payloads, and the right-rail UI adapter.
