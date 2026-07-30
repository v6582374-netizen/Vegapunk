# End-User Frontend V1 Researcher Controls

> Historical research record. These browser-oriented controls are retained for audit context only; the active product UI is the OpenWorker Desktop App.

## Decision

Version 1 exposes only settings that express a researcher's intent and already flow through the current runtime.
Deep Research exposes model and credential selection but no algorithmic tuning.
Discovery additionally exposes literature grounding, round count, round strategy, Candidate Experiment count, and Experiment Run count.
Every other current parameter remains an administrator-owned default.

Researcher Model Credentials are Provider-scoped secrets belonging to the Sole Researcher.
They are encrypted at rest, referenced by opaque identifier, decrypted only inside the trusted worker, and never copied into task files, configuration snapshots, artifacts, command arguments, environment variables, logs, events, or error bodies.

## Version 1 Allowlist

| Product setting | Existing backend field | Workflow | Product validation |
| --- | --- | --- | --- |
| Model | Unified Model Catalog `active_text_model` | Both | One administrator-approved Canonical Model Identity eligible for the workflow |
| Model Credential | New opaque `credential_id` reference | Both | Must exist and match the selected model's Provider |
| Literature grounding | `agents.generation.do_survey` | Discovery | Boolean |
| Discovery rounds | `workflow.loop_rounds` | Discovery | Integer from 1 through the administrator policy limit |
| Round strategy | `workflow.loop_mode` | Discovery | `fresh` or `incremental` |
| Candidate Experiments per round | `workflow.top_ideas_count` | Discovery | Integer from 1 through both the administrator policy limit and the effective `generation_count` |
| Experiment Runs per Candidate | `experiment.max_runs` | Discovery | Integer from 1 through the administrator policy limit |

The server supplies defaults, ranges, enums, and model availability to the frontend.
The frontend does not duplicate those policy values.
The server rejects invalid settings rather than clamping or silently substituting them.
It also enforces an administrator-defined aggregate work budget across rounds, candidates, and Experiment Runs.

The normalized values, including defaults the researcher did not change, become immutable when work is submitted.
The worker records those non-secret effective values in the work's configuration snapshot when execution begins.
Resume uses the original settings and model identities.

## Deep Research Boundary

The current Deep Research CLI forces `agents.dr.mode` to `qa` and projects the Active Text Model into every Deep Research model role.
The main Run Parameter Registry contains only `agents.dr.enabled` and `agents.dr.mode` for this workflow.
The detailed values in `config_qa.yaml` control orchestration, tools, concurrency, output, logging, and internal paths rather than stable researcher intent.

Version 1 therefore exposes no Deep Research algorithm setting.
Inputs such as the question and attachments belong to the Research Submission rather than Run Settings.
Future depth or effort controls require a separately validated product abstraction instead of exposing the internal QA configuration tree.

## Discovery Boundary

The five Discovery fields above have direct, existing effects:

- `do_survey` decides whether the generation phase invokes the Survey Agent.
- `loop_rounds` bounds the outer Discovery loop.
- `loop_mode` chooses a fresh baseline or the previous round's best result.
- `top_ideas_count` controls how many ranked ideas enter experimentation.
- `max_runs` bounds Experiment Runs for each Candidate Experiment.

The following groups remain administrator-owned:

- System, logging, paths, launchers, endpoints, protocols, headers, prompt text, and raw model catalog fields.
- Queue, retry, timeout, concurrency, GPU, and parallel experiment limits.
- Memory backends, directories, retrieval tuning, persistence, and prompt evolution.
- Agent temperatures, creativity, reflection, evolution, ranking weights, filtering thresholds, and regeneration limits.
- Tool source lists, remote MCP configuration, literature API keys, and knowledge graph endpoints.
- Evaluation mode, coding-agent backend and model, MCTS, and Paper configuration.

These values either expose infrastructure, affect resource isolation, reveal administrative configuration, or are too implementation-specific to form a stable Version 1 product contract.

## Model Selection

The Unified Model Catalog remains the administrator-owned source of Provider definitions, Canonical Model Identities, capabilities, retry policy, and concurrency policy.
Catalog presence alone does not make an entry product-visible.
The product facade applies an explicit allowlist and returns only a sanitized option projection such as model identity, display label, Provider identity, workflow eligibility, and credential requirement.

Researchers cannot submit Provider names, endpoints, protocols, headers, capability declarations, retry policy, concurrency, or arbitrary model strings.
They select one advertised Canonical Model Identity.
The server derives all required Capability Model Bindings from the approved configuration and performs the existing Capability Preflight.
The Active Text Model remains shared by every text-producing and text-evaluating role.
The Image Model remains under the same Provider as the Active Text Model, and the local Embedding Model remains service-managed.

This keeps model semantics unchanged and prevents a user-specific model registry from emerging beside the Unified Model Catalog.

## Credential Storage

Each credential record contains only the following product data:

- An opaque credential identifier.
- One approved Provider identity.
- A researcher-supplied label and masked suffix for recognition.
- Envelope-encrypted secret material and its encryption key version.
- Creation, update, and revocation timestamps.

The encryption key is held by a managed KMS or equivalent deployment secret service rather than in the application database.
The create and replace operations accept the plaintext key once and never return it.
Read operations return metadata only.
Credential list, read, replace, and revoke operations address the Sole Researcher's local credential collection.

A credential belongs to a Provider, not a model.
One credential may therefore authenticate the approved text, vision, and image models under that Provider while the server still validates every selected model and capability binding.

Version 1 requires an explicit Researcher Model Credential for every remote Provider used by product work.
It does not silently fall back to the Admin Console's service credential.
A later service-funded offering can add an administrator-issued credential source without changing the Researcher Model Credential contract.

## Credential Application

1. The researcher selects an advertised model and one of their credentials for that model's Provider.
2. Submission stores the normalized Run Settings, model identity, and credential identifier in the work record.
3. Before execution, the server rechecks Provider equality, current model approval, workflow eligibility, and revocation state.
4. The trusted worker decrypts the key into process memory and derives a per-work `ModelCatalog` from the approved catalog without mutating the global catalog.
5. The worker sets only the selected Provider's existing in-memory `api_key` slot, selects the approved Active Text Model and Capability Model Bindings, constructs one `UnifiedModelRuntime`, and injects that Runtime into all active consumers.
6. The worker releases references to the plaintext when work exits and never serializes the Runtime or its Provider settings.

The existing Runtime already accepts an in-memory Provider `api_key`, performs Canonical Model Identity and capability validation, and supplies the same Runtime to Discovery, Deep Research, Paper, memory, and nested workflows.
Credential plumbing therefore changes orchestration and transport only, not inference semantics or Provider adapters.

The current Admin `LaunchQueue` copies complete global configuration files into each launch directory.
The product facade must not reuse that copy operation unchanged.
It must materialize a product-owned, non-secret effective snapshot containing only the selected catalog subset, immutable Run Settings, and a catalog or policy version digest.
The full global catalog and configuration snapshot are never exposed through the curated researcher artifact manifest.

Secrets must also be excluded from application telemetry, exception text, progress events, queue persistence, upload metadata, and crash reports.
Candidate experiment processes must never inherit credential material.

## Rotation, Revocation, And Resume

The work record holds a credential reference rather than a secret copy.
Credential replacement changes authentication material without changing the model or research configuration.
Resume reuses the original model and settings but resolves the current secret behind the same credential reference.

If the credential is missing, revoked, assigned to another Provider, or the model is no longer approved, start or resume fails before research execution with a stable credential or policy error.
The researcher may bind another credential for the same Provider before resuming.
Changing the model or Provider requires new work.

Revocation prevents queued work and resumes from starting.
Revocation also requests graceful stop for active product work using that credential so a key removed by its owner does not remain usable for an unbounded run.

## Contract Requirements For The Next Ticket

The `product-api-contract` ticket should define:

- A sanitized model-options resource rather than access to `/api/model-catalog`.
- Credential create, list-metadata, replace, revoke, and optional validation operations for the Sole Researcher.
- Model and credential identifiers plus the allowlisted Run Settings in each create request.
- Stable errors for an unknown model, disallowed model, missing credential, Provider mismatch, revoked credential, capability failure, and policy-budget failure.
- Immutable effective settings in work responses without Provider configuration or secret metadata.
- Same-Provider credential rebinding for resume without allowing model or Run Setting edits.

## Evidence

- [`admin_console/parameters.py`](../../admin_console/parameters.py#L121) defines the current parameter schema and validation rules.
- [`launch_discovery.py`](../../launch_discovery.py#L753) consumes `loop_rounds` and `loop_mode` in the outer Discovery loop.
- [`vegapunk/mas/workflow/orchestration_agent.py`](../../vegapunk/mas/workflow/orchestration_agent.py#L480) invokes the Survey Agent when `do_survey` is enabled.
- [`vegapunk/mas/agents/ranking_agent.py`](../../vegapunk/mas/agents/ranking_agent.py#L54) consumes `top_ideas_count`.
- [`vegapunk/stage.py`](../../vegapunk/stage.py#L951) consumes `experiment.max_runs`.
- [`launch_qa.py`](../../launch_qa.py#L19) loads the catalog and forces Deep Research QA mode.
- [`vegapunk/mas/agents/dr_agent.py`](../../vegapunk/mas/agents/dr_agent.py#L134) projects the Active Text Model into every Deep Research role.
- [`vegapunk/mas/models/unified_runtime.py`](../../vegapunk/mas/models/unified_runtime.py#L115) constructs the catalog from a mapping, accepts a Provider `api_key`, and validates Provider and model invariants.
- [`admin_console/queue.py`](../../admin_console/queue.py#L212) currently snapshots complete global configuration files before launching a child process.
- [`docs/adr/0157-use-global-defaults-with-launch-start-snapshots.md`](../adr/0157-use-global-defaults-with-launch-start-snapshots.md) defines immutable start snapshots and resume behavior for Admin launches.
- [`CONTEXT.md`](../../CONTEXT.md#L104) defines the Unified Model Catalog, Researcher Model Credential, Active Text Model, and Capability Model Binding vocabulary used by this decision.
