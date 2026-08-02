# Native Desktop Discovery Module integration map

Type: map
Status: resolved
Labels: wayfinder:map

## Destination

Produce an implementation-ready product, domain, API, and migration specification for integrating Discovery as a standalone Sidebar module in the Native Desktop Application.
The specification covers the single Preparation input, multi-file and text intake, conversion and review, one active Launch with read-only history, Stop and Resume, desktop sidecar integration, and adapters for Progress, Artifacts, and Access.
This map is planning-only and does not implement production code.

## Notes

- Use `grilling`, `domain-modeling`, `prototype`, and `research` when resolving tickets.
- The canonical glossary is `CONTEXT.md`.
- The current native GUI baseline is `desktop/openworker/upstream/surfaces/gui/src/App.tsx`, `Sidebar.tsx`, `SessionIntro.tsx`, `RightRail.tsx`, `AccessSection.tsx`, and `api.ts`.
- The current native Python sidecar API is under `desktop/openworker/upstream/coworker/server/`.
- The current Discovery backend is under `admin_console/` and is not yet exposed through the native sidecar.
- Confirmed Version 1 direction: one top-level Sidebar Discovery module with internal navigation.
- Confirmed Version 1 direction: one current Preparation, multiple individually uploaded files plus free-form text, no folders, and the existing `.txt`, `.md`, `.pdf`, `.docx`, `.csv`, and `.zip` whitelist.
- Confirmed Version 1 direction: explicit conversion and review before Run, global default model settings, one active Launch, read-only Launch history, and Stop plus Resume.
- Confirmed Version 1 direction: reuse the existing Progress and Artifacts visual patterns through Discovery-specific data adapters; do not render the session-level AccessSection in Discovery V1.
- Concrete page layout is intentionally deferred to prototype tickets.
- The previous Web Unified Workspace and dual-Space decisions are outside this map and are not architecture input for the Native Desktop Application.
- Deleting historical Web planning files is a separate cleanup and is not part of this map.

## Decisions so far

<!-- Closed decision tickets appear here as one-line links. -->

- [Audit Native Desktop sidecar and Discovery service ownership](issues/01-audit-native-desktop-sidecar-and-discovery-service-ownership.md) - Native Desktop keeps one Tauri-managed authenticated sidecar; Discovery joins it under `/v1/discovery` with native state and adapters. The former `admin_console` service is retired.
- [Prototype Discovery Preparation intake and conversion flow](issues/02-prototype-discovery-preparation-intake-and-conversion-flow.md) - C Stage Canvas is selected for the single Preparation flow; completed Gather, Convert, Review, and Run stages receive a green completion-circle accent while unfinished stages stay neutral.
- [Prototype Discovery Launch monitoring and history flow](issues/03-prototype-discovery-launch-monitoring-and-history-flow.md) - Runtime Desk is selected; structured Runtime output stays central and exact durable raw console lines open as a secondary diagnostic view.
- [Define single-Preparation upload persistence and error contract](issues/04-define-single-preparation-upload-persistence-and-error-contract.md) - The whole Preparation is saved explicitly; unsaved drafts are memory-only, source intake is all-or-nothing, sources are add/delete-only, and saved state lives in Native Desktop storage.
- [Define conversion, formatted-input revision, and Run gating contract](issues/05-define-conversion-formatted-input-revision-and-run-gating-contract.md) - Conversion produces an explicit-review draft; only a saved revision can Run, edits require reconversion and save, and Run freezes a Launch Snapshot while leaving Preparation editable.
- [Map single-active Launch lifecycle and desktop transport](issues/06-map-single-active-launch-lifecycle-and-desktop-transport.md) - Native Discovery runs inside the single authenticated sidecar under `/v1/discovery`, persists one active Launch and read-only history in the app data root, uses status polling plus structured event-cursor recovery and raw-log SSE, and adopts or marks interrupted work after restart without automatic Resume.
- [Define RightRail adapter and artifact access contract](issues/07-define-rightrail-adapter-and-artifact-access-contract.md) - Discovery uses dedicated Progress and artifact adapters; Preparation hides Artifacts, active and history scope outputs to the selected Launch, file access is path-confined with safe preview or native open, and session AccessSection is omitted.
- [Define Native Desktop acceptance and migration boundary](issues/08-define-native-desktop-acceptance-and-migration-boundary.md) - Native cutover requires sidecar API, hermetic GUI, restart and reconnect, and migration-isolation P0 gates; retired `/api/workspace/*` and `/api/admin/*` families are only negative-test guards and are not called by Native GUI.
- [Native Desktop Discovery Module integration specification](issues/09-native-desktop-discovery-module-spec.md) - The resolved product, domain, sidecar, adapter, migration, and P0 acceptance contracts are consolidated into an implementation-ready handoff without changing production code.

## Not yet specified

<!-- No remaining decisions. -->

## Out of scope

- Reopening or implementing the Web Unified Workspace, dual-Space navigation, or Project Space replacement.
- Embedding Discovery in New Session conversations.
- Multiple independent Preparations, project workspaces, or parallel Discovery Launches.
- A Discovery-local model picker or new model-provider configuration surface.
- Changes to the scientific Discovery workflow, round semantics, experiment semantics, or PaperOrchestra behavior.
