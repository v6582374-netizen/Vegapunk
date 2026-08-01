# 04 - Start one immutable Discovery Launch from a saved revision

**What to build:** The Sole Researcher can confirm a valid Run from one saved Formatted Discovery Input revision, create an immutable Launch Snapshot, and see that Launch as the current record while completed or failed Launches remain read-only history.

**Blocked by:** 03 - Convert and save a reviewed Formatted Discovery Input revision.

**Status:** completed

- [x] Run is enabled only when the Preparation has valid input, a successful current Conversion, a saved non-empty revision, and no active Launch.
- [x] Run presents a long-running-operation confirmation before admission.
- [x] Admission persists the selected Preparation identity, formatted-input revision, validated source references, and effective Launch Configuration Snapshot before execution starts.
- [x] Later Preparation edits cannot change an admitted Launch Snapshot.
- [x] The sidecar enforces one active Launch atomically and returns a conflict instead of exposing a user-visible queue.
- [x] Start retries with the same idempotency key return the original result without creating a duplicate Launch, while conflicting request fingerprints are rejected.
- [x] A deterministic fake runner makes a new Launch observable through current Launch and history views.
- [x] Completed and failed Launches are selectable as read-only history, while the Preparation remains editable for a later Launch.
