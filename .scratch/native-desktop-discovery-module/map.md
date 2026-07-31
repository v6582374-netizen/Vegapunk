# Native Desktop Discovery Module integration map

Type: map
Status: open
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
- Confirmed Version 1 direction: reuse the existing Progress, Artifacts, and Access UI through Discovery-specific data adapters.
- Concrete page layout is intentionally deferred to prototype tickets.
- The previous Web Unified Workspace and dual-Space decisions are outside this map and are not architecture input for the Native Desktop Application.
- Deleting historical Web planning files is a separate cleanup and is not part of this map.

## Decisions so far

<!-- Closed decision tickets appear here as one-line links. -->

- [Audit Native Desktop sidecar and Discovery service ownership](issues/01-audit-native-desktop-sidecar-and-discovery-service-ownership.md) - Native Desktop keeps one Tauri-managed authenticated sidecar; Discovery joins it under `/v1/discovery` with native state and adapters, while `admin_console` remains a compatibility and test boundary.
- [Prototype Discovery Preparation intake and conversion flow](issues/02-prototype-discovery-preparation-intake-and-conversion-flow.md) - C Stage Canvas is selected for the single Preparation flow; completed Gather, Convert, Review, and Run stages receive a green completion-circle accent while unfinished stages stay neutral.

## Not yet specified

- The concrete Launch observation layout.
- Upload persistence, replacement, retry, and partial-failure behavior inside the single Preparation.
- Formatted-input revision storage, conversion invocation, and Run gating details.
- Native sidecar startup, storage roots, authentication, and `/v1/discovery` endpoint shape.
- Live status, log, Stop, Resume, restart-recovery, and reconnect transport behavior.
- The exact adapter interfaces and visibility rules for Progress, Artifacts, and Access.
- Native desktop acceptance, end-to-end coverage, and the boundary for removing or preserving legacy Web routes.

## Out of scope

- Reopening or implementing the Web Unified Workspace, dual-Space navigation, or Project Space replacement.
- Embedding Discovery in New Session conversations.
- Multiple independent Preparations, project workspaces, or parallel Discovery Launches.
- A Discovery-local model picker or new model-provider configuration surface.
- Changes to the scientific Discovery workflow, round semantics, experiment semantics, or PaperOrchestra behavior.
