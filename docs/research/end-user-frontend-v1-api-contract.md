# End-User Frontend V1 API Contract Inventory

## Scope

This inventory covers the current HTTP, SSE, upload, and artifact surfaces relevant to Deep Research Runs and Discovery Launches.
It distinguishes reusable backend behavior from routes that are safe to expose directly to the Sole Researcher.
It does not design the replacement product API.

For this inventory, a product-safe contract assumes one implicit Sole Researcher, requires no request identity or per-resource ownership, remains stable enough for a separate frontend, and exposes only researcher-facing data and actions.
It operates only inside the Local Product Boundary on the Sole Researcher's own machine and same-origin browser context.

## Conclusion

No existing route is safe to expose directly to the end-user product.
The Admin Console API exposes service-global tasks, queue entries, process IDs, raw logs, every artifact, prompts, models, parameters, and destructive controls.

The Discovery implementation nevertheless has reusable internal behavior for task materialization, serial enqueueing, status, graceful stop, resume, structured timelines, Experiment Run details, and path-contained artifact reads.
A product-owned facade can adapt that behavior without changing research, experiment, queue, model, or GPU logic.

Deep Research has no browser-facing contract.
Its only standalone entry point is a synchronous CLI that accepts one question and one optional local file path, then prints or writes the final answer.

The Sci evaluation server is not a product API candidate.
Its `/api/runs/*` routes execute benchmark evaluation workspaces and stream Claude Code evaluator output rather than Deep Research or Discovery work.

## Coverage Matrix

| Capability | Deep Research Run | Discovery Launch |
| --- | --- | --- |
| Start | Synchronous CLI only | Admin HTTP via task creation followed by queue submission |
| Browser upload | None | One optional baseline ZIP in the Admin task form |
| Reference material | One server-local CLI file path | No dedicated browser contract |
| Dataset upload | None | No dedicated browser contract |
| Durable ID | None | Queue ID plus launch-directory ID |
| List and history | None | Global Admin launch and queue listings |
| Status | None | Polling endpoint with string state and inferred stage |
| Live progress | None | Raw log-line SSE plus status polling |
| Cancel or stop | None | Queue cancel, graceful stop, force kill, and aborted-only resume |
| Result | Stdout or caller-selected file | Structured timeline, Experiment Run detail, and raw artifacts |
| Authentication and ownership | None | None |

## Deep Research Contract

`launch_qa.py` is the only standalone Deep Research entry point.
It accepts `--question`, an optional `--file` path, an optional `--output` path, and a project config path.
It invokes `DRAgent.execute()` synchronously and returns only after the final answer is available.

The CLI provides no run identifier, persisted run metadata, lifecycle state, progress event stream, cancellation operation, history listing, standard error body, or server-owned report artifact.
The `--file` value is a path already present on the server filesystem, not a browser upload contract.

No Admin Console route invokes `launch_qa.py` or `DRAgent` in QA mode.
The product therefore needs a new durable browser adapter around the existing Deep Research behavior.

## Discovery Admin HTTP Contracts

All routes below are unversioned and belong to the developer-facing Admin Console.
FastAPI returns failures through a `detail` field, but the routes do not define stable machine-readable product error codes.

### Submission And Launch

| Contract | Existing shape | Product disposition |
| --- | --- | --- |
| `GET /api/tasks` | Global `{tasks: TaskSummary[]}` listing | Do not expose directly |
| `POST /api/tasks` | Multipart Admin task creation | Adapt underlying task creation |
| `GET /api/queue` | Global `{entries: QueueEntry[]}` including PID and stop mode | Do not expose directly |
| `POST /api/queue` | JSON `{task}` returning a queue entry | Adapt underlying enqueue behavior |
| `GET /api/launches` | Global `{launches: LaunchSummary[]}` | Adapt to the Sole Researcher's product history |

`POST /api/tasks` accepts `name`, `system`, `task_description`, `domain`, `background`, `constraints`, and one optional `baseline_code` file.
`constraints` is a JSON-encoded list inside multipart form data.
The endpoint writes a permanent task directory in the service-global task namespace.

The task endpoint exposes the `system` prompt field, which the researcher-facing product must not expose.
It has no fields for separate reference materials or datasets.
Its baseline upload has ZIP traversal protection but no declared size, file-count, content-type, or resource limit.

Task creation and launch submission are separate calls with no product submission ID or atomic relationship.
The queue accepts only a pre-existing task name and launches `launch_discovery.py` with the existing serial queue and Launch Configuration Snapshot behavior.

### Lifecycle

| Contract | Existing shape | Product disposition |
| --- | --- | --- |
| `GET /api/launches/{launch_id}/status` | `{state, stage, rounds, recent_artifacts}` | Adapt behind the product facade and stable enums |
| `GET /api/launches/{launch_id}/logs/stream` | Raw log-line SSE | Replace with persisted Research Progress Timeline updates plus a bounded durable Research Activity Stream |
| `DELETE /api/queue/{queue_id}` | Cancel queued entry | Reuse semantics behind a product run ID |
| `POST /api/queue/{queue_id}/stop` | Graceful SIGTERM stop | Reuse semantics behind a product run ID |
| `POST /api/queue/{queue_id}/kill` | Force SIGKILL | Keep Admin-only |
| `POST /api/launches/{launch_id}/resume` | Re-enqueue an aborted launch | Reuse semantics behind the product facade |

Queue entries serialize `queue_id`, `task`, `state`, `submitted_at`, `launch_id`, `pid`, and `stopped_how`.
The current frontend type omits `pid` and `stopped_how`, so it is already weaker than the actual response.

Queue state strings are `queued`, `running`, `completed`, `failed`, `cancelled`, `interrupted`, and `aborted`.
Only `aborted` launches can currently resume.
A service restart may produce `interrupted`, which has no resume path and therefore needs an explicit product lifecycle decision.

The SSE stream emits only default `data: <raw log line>` events.
It has no event types, event IDs, replay cursor, heartbeat, structured terminal event, or reconnect continuity.
Each reconnection starts reading the selected log from byte zero, so the Admin frontend can receive duplicate history after reconnecting.
The `file` query parameter can select any path-contained launch file, which is appropriate for an administrator but not a curated product stream.

### Results And Artifacts

| Contract | Existing shape | Product disposition |
| --- | --- | --- |
| `GET /api/launches/{launch_id}/timeline` | Stage, rounds, candidates, runs, and paper presence | Reuse as an internal projection |
| `GET /api/launches/{launch_id}/experiment-run?path=...` | Outcome, arbitrary metrics, log preview, files, and code diff | Reuse as an internal projection |
| `GET /api/artifacts/{launch_id}/tree` | Recursive tree of every launch file | Keep Admin-only |
| `GET /api/artifacts/{launch_id}/file?path=...` | Raw `FileResponse` with guessed media type | Reuse internally only when resolving a Curated Research Artifact |

Artifact path resolution prevents reads from escaping the selected launch directory.
That containment check is reusable, but it does not decide which artifacts are suitable for researchers.

The timeline and Experiment Run detail are useful structured overlays on filesystem artifacts.
Their fields are not declared as backend response models, and several values remain open strings or arbitrary JSON.
The product contract must stabilize only the fields needed by the researcher experience.

### Admin-Only Configuration

The product must not consume `/api/prompts*`, `/api/model-catalog`, or `/api/parameters`.
Those routes expose the Prompt Library, provider catalog, credentials-adjacent configuration, and service-global runtime parameters reserved for developers.

## Missing Browser Contracts

### Shared Boundary

- One implicit Sole Researcher with no request identity or per-resource ownership
- A Local Product Boundary that excludes LAN, public, cross-origin, and untrusted host access
- Stable workflow and lifecycle discriminators instead of free-form strings
- Versioned request, response, and machine-readable error schemas
- Upload size, count, type, extraction, quota, and retention rules
- A curated artifact manifest rather than unrestricted filesystem discovery

### Deep Research Runs

- Create a durable run from a research question and browser attachments
- Return a stable run ID before long-running work begins
- Persist queued, running, completed, failed, and stopped outcomes
- Expose a persisted Research Progress Timeline and a live Research Activity Stream without leaking internal reasoning or raw logs
- Stop an active run and define whether any form of resume exists
- Treat stop, interruption, and failure as terminal for that Run; Run Again creates a new Deep Research Run
- Retrieve the cited report and its approved supporting artifacts
- Address every Curated Research Artifact by opaque identity rather than filesystem path
- List prior Deep Research Runs

### Discovery Launches

- Accept the Research Submission fields without exposing `system` or task-directory concepts
- Upload and bind reference materials, datasets, and optional baseline code
- Translate one product submission into the existing task layout and serial queue
- Return one product-facing Launch identity rather than exposing queue IDs and filesystem IDs
- Expose history, status, stop, resume, progress, and results only through the curated product facade
- Define product behavior for the existing `interrupted` state
- Resume stopped and reconciled-incomplete Interrupted Launches by adding an Execution Attempt at the current milestone
- Treat failed Launches as terminal; rerunning creates a new Discovery Launch
- Expose selected reports, papers, figures, metrics, and reproducibility artifacts without exposing the full Admin artifact tree
- Provide a sanitized Reproducibility Bundle instead of a complete Launch workspace archive

## Reusable Backend Seams

The product facade should call the existing `LaunchQueue` rather than create a second queue.
It should preserve the existing FIFO, single-running-Launch, graceful-stop, snapshot, and resume semantics.

The facade may reuse `create_task()` as an internal translation target after product input validation and upload staging.
It should not expose the Admin task request shape.

The facade may reuse `scan_launches()`, `infer_stage()`, `count_rounds()`, `build_timeline()`, and `build_experiment_run_detail()` as implementation helpers.
These filesystem-derived projections remain internal until the product contract selects and types their stable fields.

The facade may reuse `resolve_launch_dir()`, `resolve_artifact()`, and `guess_media_type()` for authorized artifact delivery.
It should never make the recursive Admin artifact tree the researcher-facing contract.

Deep Research should continue invoking the existing `DRAgent` QA path.
The missing work is durable orchestration and product transport, not a second research engine.

## Follow-Up Decision

A separate `product-api-contract` ticket is required before the core-flow prototype.
That ticket should define the smallest local-only, unauthenticated, sole-researcher resource model that covers creation, upload, lifecycle, events, stop, history, and curated results for both workflows.

## Evidence

- [`launch_qa.py`](../../launch_qa.py#L45) defines the synchronous Deep Research CLI.
- [`admin_console/app.py`](../../admin_console/app.py#L88) defines every Admin Console HTTP and SSE route.
- [`admin_console/tasks.py`](../../admin_console/tasks.py#L56) defines task materialization and baseline ZIP extraction.
- [`admin_console/queue.py`](../../admin_console/queue.py#L25) defines queue state, persistence, stop, and resume behavior.
- [`admin_console/live.py`](../../admin_console/live.py#L59) defines the raw log-line SSE generator.
- [`admin_console/artifacts.py`](../../admin_console/artifacts.py#L18) defines launch and artifact path containment.
- [`admin_console/structured_views.py`](../../admin_console/structured_views.py#L27) defines timeline and Experiment Run projections.
- [`admin_console/frontend/src/api.ts`](../../admin_console/frontend/src/api.ts#L1) records the current Admin frontend's assumed response shapes.
- [`sci_tasks/evaluation/server.py`](../../sci_tasks/evaluation/server.py#L173) defines the separate benchmark evaluation server.

The focused Admin API suite passed 37 tests with `python -m unittest` after replacing a timing sleep in the force-kill test with runner-readiness synchronization.
