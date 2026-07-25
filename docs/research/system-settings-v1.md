# System Settings V1

Status: agreed draft

## Scope

System Settings contains exactly three submodules: Provider Connections, Prompt Library, and Default Configuration.
The top-level Skill Management Workspace Module remains reserved for future Researcher Skills and is outside this specification.

## Shared Activation Rules

An explicit successful save is the persistence boundary for every setting.
Saved changes become eligible when the next new Deep Research Run or Discovery Launch starts.
Work already running retains the settings resolved at its own start.
Queued work reads the latest successfully saved settings when it actually starts.
System Settings remains editable while work is running or resumable; no Configuration Lock is introduced.

A Launch Resume retains the original Launch Configuration Snapshot for Prompt content, Canonical Model Identities, and run parameters.
Each resumed Execution Attempt resolves the current Provider Connection for its originally bound Provider because secrets never enter the snapshot.

## Provider Connections

Provider Connections manage BYOK connectivity for the fixed Active Provider Set rather than editing the Unified Model Catalog.
Version 1 supports `relay` and `qwen` and stores at most one Researcher Model Credential per Provider.
The Sole Researcher may configure the API key and only those endpoint fields that a Provider explicitly declares user-configurable.
Protocol, capability declarations, model definitions, retry policy, concurrency policy, and default model selection remain outside this submodule.

Credentials persist through a Secret Store abstraction backed by the operating system credential vault, as recorded in ADR-0160.
Project files, databases, logs, exports, research artifacts, and configuration snapshots never contain plaintext credentials.
Read operations expose only whether a credential is configured and whether the effective source is `vault`, `environment`, or `missing`.
A stored credential takes precedence, and the supported environment variable is consulted only when no stored credential exists.
Saving a new credential replaces the preceding stored credential for that Provider.

Credential saving and online verification are separate operations.
Verification records `unverified`, `valid`, `authentication_failed`, or `unreachable` against the current credential and endpoint.
A failed probe does not prevent credential persistence and does not delete the credential.

Default Configuration may reference a Provider whose connection is not ready.
That configuration remains structurally valid but is reported as not ready.
Capability Preflight freshly validates the required connection before execution and blocks the work before research stages begin when validation still fails.
The runtime never responds by silently changing the Provider, model, or credential.

## Prompt Library

The Prompt Library contains every Registered Prompt used by Vegapunk, including scientific behavior and infrastructure prompts.
Registered Prompt identities, display metadata, orchestration metadata, and template contracts are maintained by the installed system version.
System Settings may edit Prompt bodies but cannot create, delete, rename, reorder, or disable Registered Prompts.

The prompt catalog explicitly declares each Prompt's workflow, stage, group-local first-call order, invocation type, optional mutual-exclusion group, description, and template variables.
The product groups Prompts by workflow and stage instead of presenting a false global execution sequence.
Catalog validation and tests ensure that runtime Prompt IDs are registered and that required metadata is complete.

Editing creates a Pending Prompt Revision with no runtime effect.
Explicit save validates non-empty content, template syntax, allowed variables, and required variables.
A successful save atomically replaces the Prompt's repository source file, and a failed save leaves the preceding source unchanged.
Version 1 does not detect external file edits made after the Prompt was loaded.

Saved Prompt revisions have no built-in history, separate original copy, or automatic restore operation.
Repository history owns recovery after a successful save.
Launch Configuration Snapshots preserve the effective Prompt text used by historical Launches but never write it back into the global library.

## Default Configuration

Default Configuration manages the three root Capability Model Bindings and the complete Run Parameter Registry.
The bindings are `active_text_model`, `image_model`, and `embedding_model`, and each value is a Canonical Model Identity from the fixed Unified Model Catalog.
The text and image bindings must belong to the same Provider, while the embedding binding may use another Provider.
Experiment Backend selection remains independent from model Provider selection.

The Run Parameter Registry contains every intentionally configurable parameter with a stable identity, default, description, type, and validation rule.
Secrets, internal paths, protocols, and implementation constants do not belong to the Registry.
Allowlisted Researcher Run Settings may override selected defaults for one Run without changing the Registry.

One save produces one Default Configuration Revision containing all changed model bindings and run parameter defaults.
The server validates individual fields and cross-field constraints before committing the Revision.
The entire Revision succeeds or the preceding Revision remains authoritative.
A new Run captures one complete Revision and never observes a partially written change.

Structural validity and Configuration Readiness remain separate.
A structurally valid Revision may be saved before its required Provider Connection is ready, while Capability Preflight prevents execution until the connection validates.

## Version 1 Exclusions

- Arbitrary Provider registration or model catalog editing.
- Multiple named credentials or credential rotation pools for one Provider.
- Raw YAML or arbitrary configuration-tree editing.
- Prompt creation, deletion, renaming, disabling, or user-defined orchestration.
- Prompt autosave, built-in revision history, or a separate Prompt Override layer.
- Optimistic conflict detection for external Prompt file changes.
- A global Configuration Lock tied to active or resumable research work.
