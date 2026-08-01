# 05 - Control one Launch with Stop, Resume, and restart reconciliation

**What to build:** The Sole Researcher can gracefully Stop an active Discovery Launch, Resume a stopped or reconciled interrupted Launch as a new Execution Attempt on the same Launch record, and recover safely when the sidecar or Tauri process restarts.

**Blocked by:** 04 - Start one immutable Discovery Launch from a saved revision.

**Status:** completed

- [x] The public lifecycle exposes `starting`, `running`, `stopping`, `stopped`, `interrupted`, `completed`, and `failed` with valid state transitions.
- [x] Graceful Stop persists a checkpoint, reaches `stopped`, and remains idempotent when repeated.
- [x] Resume is available only for `stopped` or reconciled `interrupted` Launches and is rejected for running or terminal history.
- [x] Resume reuses the original Launch ID and input/configuration snapshots while appending a distinct Execution Attempt.
- [x] Resume retries with the same idempotency key return the first result without adding another attempt, while conflicting fingerprints are rejected.
- [x] A matching live runner is adopted after sidecar restart without starting a second runner.
- [x] A missing or mismatched runner without a trusted terminal outcome becomes `interrupted` with its checkpoint and raw log preserved.
- [x] Sidecar restart, Tauri restart, and WebView reconnect never trigger automatic Resume.
- [x] The Native GUI exposes state-appropriate Stop and Resume actions and explains unavailable transitions.
