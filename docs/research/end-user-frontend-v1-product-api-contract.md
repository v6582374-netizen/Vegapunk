# End-User Frontend V1 Product API Contract

## Decision

Version 1 adds a separate product facade under `/api/v1`.
It does not expose or rename the Admin Console API.

The product runs only inside the Local Product Boundary.
It has one implicit Sole Researcher and no authentication, identity, invitation, account, tenant, or ownership fields.
The server listens only on loopback interfaces, serves the frontend and API from one origin, rejects untrusted hosts and cross-origin browser requests, and enables no permissive CORS policy.

Deep Research Runs and Discovery Launches remain separate top-level resources.
They share lifecycle, progress, activity, error, and artifact shapes without introducing a generic public `work` resource or combined history endpoint.

Creation atomically validates the submission, claims its Staged Research Uploads, persists a durable product identity, and schedules execution.
There is no server-side Draft resource or separate Start command.

## Resource Map

| Resource | Purpose | Lifetime |
| --- | --- | --- |
| Work Options | Sanitized models, defaults, setting constraints, and upload policy | Read from current administrator policy |
| Researcher Model Credential | Provider-scoped secret selected for model calls | Until replaced or revoked |
| Staged Research Upload | One temporary input file waiting to be claimed | Until claimed, deleted, or expired |
| Deep Research Run | Durable question investigation and cited report | Persistent product history |
| Discovery Launch | Durable queued discovery, experiments, and Paper output | Persistent product history |
| Research Progress Timeline | Ordered durable core milestones for one Run or Launch | Same lifetime as its work |
| Research Activity Stream | Bounded durable terminal-style output for one Run or Launch | Oldest messages may expire at the product limit |
| Curated Research Artifact | Stable product-visible output addressed by opaque identity | Same retention as its work |

## Protocol Conventions

All endpoints use `/api/v1`.
Requests and responses use UTF-8 JSON except one-file multipart uploads, SSE event streams, and artifact bodies.
Timestamps are RFC 3339 UTC strings.
Identifiers are opaque strings and never encode task names or filesystem paths.

List endpoints return:

```json
{
  "items": [],
  "next_cursor": null
}
```

Lists use opaque cursor pagination with a server-capped `limit`.
Work history defaults to active work first and then newest creation time.

Work creation and Run Again requests require an `Idempotency-Key` header.
Repeating a request with the same key and same body returns the original result without creating duplicate work.
Reusing the key with another body returns `409 idempotency_conflict`.

The product never returns process IDs, queue IDs, filesystem paths, raw exception text, Provider endpoints, secret field names, hidden prompts, or Admin resource URLs.

## Work Options

`GET /api/v1/work-options` is the only browser-facing configuration discovery endpoint.
It returns a sanitized projection rather than the Unified Model Catalog or Run Parameter Registry.

```json
{
  "models": [
    {
      "id": "relay/gpt-5.6-sol",
      "label": "GPT 5.6",
      "provider_id": "relay",
      "provider_label": "Relay",
      "workflows": ["deep_research", "discovery"],
      "credential_required": true
    }
  ],
  "defaults": {
    "deep_research_model_id": "relay/gpt-5.6-sol",
    "discovery_model_id": "relay/gpt-5.6-sol"
  },
  "discovery_settings": {
    "literature_grounding": {"type": "boolean", "default": true},
    "discovery_rounds": {"type": "integer", "minimum": 1, "maximum": 10, "default": 10},
    "round_strategy": {"type": "enum", "values": ["fresh", "incremental"], "default": "incremental"},
    "candidate_count": {"type": "integer", "minimum": 1, "maximum": 5, "default": 5},
    "experiment_run_limit": {"type": "integer", "minimum": 1, "maximum": 2, "default": 2}
  },
  "upload_policy": {
    "purposes": ["reference", "dataset", "baseline_code"],
    "maximum_files_per_purpose": {
      "reference": 20,
      "dataset": 5,
      "baseline_code": 1
    },
    "maximum_bytes_per_file": {
      "reference": 52428800,
      "dataset": 536870912,
      "baseline_code": 104857600
    },
    "accepted_media_types": {
      "reference": ["application/pdf", "text/plain", "text/markdown"],
      "dataset": ["text/csv", "application/json", "application/zip"],
      "baseline_code": ["application/zip"]
    },
    "maximum_unclaimed_bytes": 1073741824,
    "unclaimed_ttl_seconds": 86400
  }
}
```

The values above illustrate the contract shape rather than fixed frontend defaults.
The server response is authoritative, and the frontend must not hardcode them.
Each upload-policy object contains an entry for every advertised purpose, even when a purpose currently accepts no media type.

The product setting keys map internally as follows:

| Product key | Existing field |
| --- | --- |
| `literature_grounding` | `agents.generation.do_survey` |
| `discovery_rounds` | `workflow.loop_rounds` |
| `round_strategy` | `workflow.loop_mode` |
| `candidate_count` | `workflow.top_ideas_count` |
| `experiment_run_limit` | `experiment.max_runs` |

## Credentials

| Method and path | Behavior |
| --- | --- |
| `GET /api/v1/credentials` | List credential metadata |
| `GET /api/v1/credentials/{credential_id}` | Read one credential's metadata |
| `POST /api/v1/credentials` | Store one Provider credential |
| `PATCH /api/v1/credentials/{credential_id}` | Rename or replace the secret |
| `DELETE /api/v1/credentials/{credential_id}` | Revoke the credential and remove usable secret material |

Create accepts:

```json
{
  "provider_id": "relay",
  "label": "Personal Relay Key",
  "api_key": "secret"
}
```

Credential responses contain only `id`, `provider_id`, `label`, `masked_suffix`, `created_at`, `updated_at`, and `revoked_at`.
The plaintext secret is write-only.
Patch accepts `label`, `api_key`, or both and rejects an empty body.

Revocation blocks queued starts and resumes that reference the credential.
Revoking a credential used by active work requests Graceful Stop.
A resume may bind another credential for the same Provider, but it may not change the selected model or Provider.

## Staged Uploads

| Method and path | Behavior |
| --- | --- |
| `POST /api/v1/uploads` | Accept one multipart file and return a Staged Research Upload |
| `DELETE /api/v1/uploads/{upload_id}` | Delete an unclaimed upload |

`POST /api/v1/uploads` accepts a `purpose` field and one `file` field.
The allowed purposes are `reference`, `dataset`, and `baseline_code`.

```json
{
  "id": "upl_01...",
  "purpose": "reference",
  "name": "prior-work.pdf",
  "media_type": "application/pdf",
  "size_bytes": 482031,
  "created_at": "2026-07-21T08:00:00Z",
  "expires_at": "2026-07-22T08:00:00Z"
}
```

Each upload is claimed atomically by exactly one created Run or Launch.
A claim moves the bytes into that work's immutable retained inputs so Run Again does not depend on the temporary upload lifetime.
A missing, expired, already claimed, wrong-purpose, oversized, or unsupported upload rejects creation without creating work.
Baseline code must satisfy the ZIP extraction limits before a Discovery Launch is enqueued.
Unclaimed uploads expire automatically.

Version 1 does not provide upload listing, cross-work reuse, chunked upload, or resumable byte transfer.

## Common Work Shape

Deep Research Run and Discovery Launch responses share these fields:

```json
{
  "id": "dr_01...",
  "workflow": "deep_research",
  "title": "Derived concise title",
  "state": "running",
  "created_at": "2026-07-21T08:00:00Z",
  "started_at": "2026-07-21T08:00:02Z",
  "ended_at": null,
  "model": {
    "id": "relay/gpt-5.6-sol",
    "provider_id": "relay"
  },
  "credential": {
    "id": "cred_01...",
    "label": "Personal Relay Key",
    "provider_id": "relay"
  },
  "settings": {},
  "allowed_actions": ["stop"],
  "progress": {},
  "activity": {},
  "artifacts": [],
  "error": null,
  "source_work_id": null
}
```

The response stores normalized effective settings, including server defaults omitted by the create request.
No mutable update endpoint exists for submissions, models, or settings.
`started_at` records the first execution start for the identity.
`ended_at` is set only while the work is terminal and returns to `null` when a Discovery Resume reopens the Launch; milestone attempts retain the earlier execution timestamps.

## Lifecycle

The public work states are:

| State | Meaning | Product actions |
| --- | --- | --- |
| `queued` | Durable work is waiting to start | `stop` |
| `running` | A worker owns execution | `stop` |
| `stopping` | Graceful Stop was accepted | None |
| `completed` | The workflow completed successfully | `run_again` |
| `failed` | Execution ended with a sanitized failure | `run_again` |
| `cancelled` | Work was stopped before execution began | `run_again` |
| `stopped` | Active work ended through Graceful Stop | Discovery: `resume`, `run_again`; Deep Research: `run_again` |
| `interrupted` | Execution ownership ended without a trustworthy outcome | Discovery after reconciliation: `resume`, `run_again`; Deep Research: `run_again` |

`allowed_actions` is authoritative.
The frontend does not infer actions from state.

When a Discovery Launch becomes `interrupted`, the facade first reconciles durable completion markers.
It changes the state to `completed` if completion is proven.
Otherwise it preserves `interrupted` and permits explicit Resume.
The product never resumes automatically.

Discovery Resume preserves the Launch identity, original effective configuration, completed milestones, and prior Execution Attempts.
It adds a new Execution Attempt at the current milestone and re-enters `queued`.

Deep Research has no Resume endpoint because the existing QA path has no reliable Workflow Progress checkpoints.
Run Again always creates a new identity and records `source_work_id`.
Failed Discovery Launches also use Run Again rather than Resume.

## Deep Research Runs

| Method and path | Behavior |
| --- | --- |
| `GET /api/v1/deep-research-runs` | List Deep Research history |
| `POST /api/v1/deep-research-runs` | Create and schedule a Run |
| `GET /api/v1/deep-research-runs/{run_id}` | Read detail, progress, result, and artifact manifest |
| `POST /api/v1/deep-research-runs/{run_id}/stop` | Cancel queued work or request Graceful Stop |
| `POST /api/v1/deep-research-runs/{run_id}/run-again` | Create a new Run from the immutable prior submission |
| `GET /api/v1/deep-research-runs/{run_id}/events` | Stream progress and activity events with SSE |
| `GET /api/v1/deep-research-runs/{run_id}/activity` | Page through retained terminal-style output |
| `GET /api/v1/deep-research-runs/{run_id}/artifacts/{artifact_id}` | Read or download one Curated Research Artifact |

Create accepts:

```json
{
  "question": "What evidence supports ...?",
  "reference_upload_id": "upl_01...",
  "model_id": "relay/gpt-5.6-sol",
  "credential_id": "cred_01..."
}
```

`reference_upload_id` is optional and accepts at most one reference because the existing Deep Research entry point accepts one file.
The server derives the history title from the question.
Successful detail includes a cited report summary, structured source references where available, and report artifact identities.

## Discovery Launches

| Method and path | Behavior |
| --- | --- |
| `GET /api/v1/discovery-launches` | List Discovery history |
| `POST /api/v1/discovery-launches` | Create and enqueue a Launch |
| `GET /api/v1/discovery-launches/{launch_id}` | Read detail, progress, summary, and artifact manifest |
| `POST /api/v1/discovery-launches/{launch_id}/stop` | Cancel queued work or request Graceful Stop |
| `POST /api/v1/discovery-launches/{launch_id}/resume` | Re-enqueue a stopped or reconciled-incomplete Interrupted Launch |
| `POST /api/v1/discovery-launches/{launch_id}/run-again` | Create a new Launch from the immutable prior submission |
| `GET /api/v1/discovery-launches/{launch_id}/events` | Stream progress and activity events with SSE |
| `GET /api/v1/discovery-launches/{launch_id}/activity` | Page through retained terminal-style output |
| `GET /api/v1/discovery-launches/{launch_id}/results` | Read structured rounds, candidates, metrics, and Paper summary |
| `GET /api/v1/discovery-launches/{launch_id}/candidate-experiments/{candidate_id}` | Read Candidate Experiment and Experiment Run detail |
| `GET /api/v1/discovery-launches/{launch_id}/artifacts/{artifact_id}` | Read or download one Curated Research Artifact |

Create accepts:

```json
{
  "brief": {
    "goal": "Improve ...",
    "domain": "...",
    "background": "...",
    "constraints": ["..."]
  },
  "uploads": {
    "reference_ids": ["upl_01..."],
    "dataset_ids": ["upl_02..."],
    "baseline_code_id": "upl_03..."
  },
  "model_id": "relay/gpt-5.6-sol",
  "credential_id": "cred_01...",
  "settings": {
    "literature_grounding": true,
    "discovery_rounds": 10,
    "round_strategy": "incremental",
    "candidate_count": 5,
    "experiment_run_limit": 2
  }
}
```

The facade translates this request into the existing task layout and Launch Queue submission without exposing `system`, task names, queue IDs, launch-directory IDs, or Experiment Backend selection.
Create validates the server's aggregate work budget across rounds, candidates, and Experiment Runs.

Resume accepts an optional replacement `credential_id` for the original Provider.
It rejects model, Provider, setting, brief, or upload changes.

## Progress Timeline

The server supplies the ordered milestones and progress percentage.
The frontend never derives workflow completion from filenames or raw logs.

```json
{
  "revision": 17,
  "percent": 42,
  "current_milestone_id": "ms_04",
  "milestones": [
    {
      "id": "ms_04",
      "key": "evidence_synthesis",
      "label": "Synthesize evidence",
      "position": 4,
      "state": "active",
      "summary": "18 sources retained",
      "started_at": "2026-07-21T08:04:00Z",
      "ended_at": null,
      "attempts": [
        {
          "number": 1,
          "state": "active",
          "started_at": "2026-07-21T08:04:00Z",
          "ended_at": null,
          "summary": null
        }
      ]
    }
  ]
}
```

Milestone states are `pending`, `active`, `completed`, `failed`, `stopped`, and `interrupted`.
Earlier completed milestones remain completed when later work stops or fails.
Future milestones remain pending.
Resume adds an attempt under the affected milestone rather than overwriting its history.

## Activity Stream

Retained activity messages have this shape:

```json
{
  "sequence": 381,
  "occurred_at": "2026-07-21T08:04:03Z",
  "level": "info",
  "milestone_id": "ms_04",
  "text": "Reviewing source 12 of 18"
}
```

`GET .../activity` pages backward through retained messages.
Its response includes `oldest_sequence`, `newest_sequence`, `truncated_before_sequence`, `items`, and `next_cursor`.
The server may discard the oldest activity messages at the configured byte or message limit.
Timeline milestones and their state history are never discarded by the activity limit.

Messages are plain text with a severity of `info`, `warning`, or `error`.
The product does not transport arbitrary ANSI control sequences.
Every message passes redaction before persistence and publication.

## Event Stream

Each work exposes one SSE connection that multiplexes lifecycle, timeline, activity, and artifact notifications.

```text
id: 184
event: progress.milestone.updated
data: {"milestone": {"id": "ms_04", "state": "completed"}}
```

The event envelope uses a monotonically increasing per-work `id` and one of these event types:

- `work.state.updated`
- `progress.milestone.updated`
- `activity.appended`
- `artifact.available`
- `stream.reset`

Timeline and lifecycle updates remain replayable for the work's lifetime.
Activity updates remain replayable while their messages remain inside the bounded Activity Stream.
The browser reconnects with `Last-Event-ID`.

If the requested cursor predates retained activity, the server emits `stream.reset` with the current work shape and retained activity boundary before continuing live delivery.
The server sends heartbeat comments often enough to detect a dead connection.
A terminal work-state event closes the stream after all earlier updates have been flushed.

Raw Admin logs, model chain-of-thought, hidden prompts, Provider payloads, credentials, filesystem paths, and unredacted exceptions are forbidden event content.

## Results

Completed Deep Research detail exposes the cited report as a Curated Research Artifact and a source list containing stable titles, URLs or identifiers, and citation metadata when available.
The API does not expose model reasoning traces or intermediate prompt transcripts.

Discovery `results` returns:

- Discovery Rounds in execution order.
- Candidate Experiment summaries within each round.
- Stable Candidate and Experiment Run identities rather than paths.
- Primary and secondary metrics with value, unit, direction, baseline, and delta where available.
- Terminal Candidate Selection and its provenance where available.
- Paper editions, figures, and supporting Curated Research Artifacts.
- One Reproducibility Bundle when a selected experimental result can be packaged safely.

Candidate Experiment detail contains its hypothesis, method summary, state, metrics, ordered Experiment Runs, code difference, and Curated Research Artifact metadata.
Arbitrary backend metric JSON is normalized into typed entries and retained internally when it cannot be represented safely.

## Artifacts

Work detail includes its artifact manifest:

```json
{
  "id": "art_01...",
  "kind": "report",
  "name": "research-report.pdf",
  "media_type": "application/pdf",
  "size_bytes": 183920,
  "sha256": "...",
  "created_at": "2026-07-21T09:00:00Z",
  "disposition": "inline"
}
```

Artifact kinds are a stable product enum such as `report`, `source_manifest`, `paper`, `figure`, `metrics`, `code`, `code_diff`, and `reproducibility_bundle`.
The server resolves an artifact identity to an allowlisted contained path internally.
Requests never accept a path parameter.

Responses set a safe `Content-Type`, `Content-Length`, `Content-Disposition`, `ETag`, and `X-Content-Type-Options: nosniff`.
The product never returns the complete launch tree or complete workspace archive.

## Commands

Stop is idempotent while work is queued, running, stopping, cancelled, or stopped.
Stopping queued work produces `cancelled`.
Stopping running work returns `202`, enters `stopping`, and uses the existing Graceful Stop behavior.
Force kill remains Admin-only.

Run Again returns `201` with a new resource and reuses retained immutable inputs server-side.
It may accept a replacement credential for the same Provider.
It never reuses a work identity.

Resume returns `202` with the same Discovery Launch identity in `queued` state.
It returns `409 resume_not_available` when the Launch state, snapshot, checkpoint, model approval, or credential cannot support resume.

## Errors

Synchronous failures use one envelope:

```json
{
  "error": {
    "code": "credential_provider_mismatch",
    "message": "The selected credential does not match the selected model provider.",
    "field": "credential_id",
    "details": {},
    "request_id": "req_01..."
  }
}
```

Stable product codes include:

- `invalid_request`
- `validation_failed`
- `idempotency_conflict`
- `upload_not_found`
- `upload_expired`
- `upload_already_claimed`
- `unsupported_upload`
- `upload_too_large`
- `model_not_allowed`
- `model_capability_unavailable`
- `credential_not_found`
- `credential_provider_mismatch`
- `credential_revoked`
- `work_budget_exceeded`
- `invalid_transition`
- `resume_not_available`
- `artifact_not_found`
- `provider_authentication_failed`
- `internal_error`

An unknown or non-product-visible model identifier returns the same `model_not_allowed` error so the product does not reveal hidden catalog entries.
`model_capability_unavailable` reports a failed Capability Preflight without exposing the hidden catalog or Provider configuration.
Field validation uses `422`, missing resources use `404`, upload size uses `413`, unsupported media uses `415`, and invalid state transitions or idempotency conflicts use `409`.
Unexpected failures use a generic `500 internal_error` and record diagnostic detail only in Admin logs.

Asynchronous work failure stores the same sanitized code and message in the work resource and emits a terminal state update.
No error contains a secret, raw Provider response, prompt, local path, stack trace, or arbitrary exception string.

## Deliberate Version 1 Exclusions

- Authentication, invitations, accounts, roles, tenants, and ownership fields.
- LAN, public, or cross-origin access.
- A generic Work endpoint or combined history list.
- Server-side drafts, separate Start commands, and post-create edits.
- Chunked uploads, resumable byte transfer, and reusable file libraries.
- WebSockets; SSE covers one-way progress delivery.
- Deep Research Resume.
- Automatic Discovery Resume.
- Product force kill.
- Full artifact trees, arbitrary file paths, complete workspace archives, and raw Admin logs.
- Prompt Library, Unified Model Catalog, Run Parameter Registry, queue, PID, and Experiment Backend endpoints.
- Hard deletion of completed work; V1 preserves research history until administrator cleanup.

## Existing Backend Seams

The facade calls the existing `LaunchQueue` for Discovery instead of creating a second Discovery queue.
It translates one Discovery create request into task materialization and one queue submission while preserving FIFO, single-running-Launch, Graceful Stop, snapshot, and resume behavior.

Deep Research orchestration wraps the existing `DRAgent` QA path with a durable product identity, process lifecycle, progress timeline, activity stream, and report artifact.
It does not create another research engine.

The facade may reuse existing launch scanning, stage inference, timeline, Experiment Run projection, and contained artifact resolution as internal helpers.
Those filesystem-derived shapes are never the public contract.

The product worker constructs one per-work Unified Model Runtime from the approved catalog and Researcher Model Credential in memory.
No secret or full catalog is serialized into product records, configuration snapshots, events, or artifacts.

## Evidence

- [API Contract Inventory](end-user-frontend-v1-api-contract.md) records the current browser and backend gaps.
- [Researcher Controls](end-user-frontend-v1-researcher-controls.md) defines the allowlisted settings and credential boundary.
- [`CONTEXT.md`](../../CONTEXT.md) defines the canonical product and workflow vocabulary used here.
- [`admin_console/app.py`](../../admin_console/app.py#L88) exposes the current Admin routes that remain separate.
- [`admin_console/queue.py`](../../admin_console/queue.py#L57) provides the existing Discovery queue and resume seam.
- [`admin_console/tasks.py`](../../admin_console/tasks.py#L56) provides the current task materialization target.
- [`admin_console/structured_views.py`](../../admin_console/structured_views.py#L27) provides internal Discovery result projections.
- [`launch_qa.py`](../../launch_qa.py#L19) provides the existing Deep Research QA entry point.
