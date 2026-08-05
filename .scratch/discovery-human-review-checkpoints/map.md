# Configurable Discovery Human Review Checkpoints map

Type: map
Status: open
Labels: wayfinder:map

## Destination

Produce an implementation-ready product, domain, CLI, Native Preparation, checkpoint, and acceptance specification for adding three optional Human Review Checkpoints to the current Discovery Launch.
The finished route must define the MAS ranking/feedback checkpoint, the pre-experiment method checkpoint, and the pre-PaperOrchestra handoff checkpoint, while preserving the default fully automatic run when all options are absent or false.
Version 1 presents read-only checkpoint artifacts and requires one explicit human Resume; artifact editing and the discarded round-review seam are outside this destination.
This map is planning-only and does not implement production code.

## Notes

- Consult `grilling`, `domain-modeling`, `codebase-design`, and `prototype` when resolving tickets.
- The canonical glossary is `CONTEXT.md`.
- The three Human Review Launch Options are one configuration model exposed through optional CLI arguments and the Native Desktop Discovery Preparation surface; there is no separate Settings module or separate CLI/Native policy model.
- Every new Launch defaults all three options to false. Explicit selections are copied into the immutable Launch configuration snapshot and are not implicitly carried to the next Launch.
- An enabled seam creates an inactive, durable Human Review Checkpoint. The user sees read-only artifacts and explicitly presses the single `Resume` action; there is no live background wait or automatic continuation.
- The MAS checkpoint is created on every MAS entry into `AWAITING_FEEDBACK` after ranking. The method checkpoint is one per round after all refined methods are available and before the execution/reporting path. The handoff checkpoint is one per Launch after Discovery summary creation and before PaperOrchestra starts.
- The three seam presentations are intentionally distinct and will be discussed separately; no universal review editor is assumed.
- The current CLI orchestration is in `launch_discovery.py`; MAS state and feedback are in `vegapunk/mas/`; Native preparation/launch lifecycle is under `desktop/openworker/upstream/coworker/server/` and `surfaces/gui/`.

## Decisions so far

<!-- Closed decision tickets appear here as one-line links. -->

## Not yet specified

- Canonical flag names, serialization, and how Preparation controls are carried into the Run request and Launch snapshot.
- The shared checkpoint record, state transitions, durable artifact manifest, explicit Resume operation, and restart/idempotency rules across current CLI and Native adapters.
- The exact read-only artifact bundle, user-visible questions, and implementation seam for each of the three checkpoint types.
- How MAS feedback is represented in Version 1 when checkpoint artifacts are read-only and Resume is the only action; future editing/feedback mutation is deferred.
- The exact compatibility and acceptance matrix for disabled options, enabled options, CLI invocation, Preparation Run, failure, restart, and completed history.

## Out of scope

- The previously proposed `每轮实验结束、经验/baseline 更新前` checkpoint.
- A standalone Settings module for Human Review controls.
- Persisting or implicitly reusing the previous Launch's option values.
- Editing, saving, or creating revisions of checkpoint artifacts in Version 1.
- Changing experiment semantics, incremental baseline semantics, MAS algorithms, or PaperOrchestra's internal writing loop.
- Multiple independent Preparations, parallel Discovery Launches, or a per-task Human Review policy.
