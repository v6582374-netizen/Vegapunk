---
status: superseded by ADR-0025
---

# Opt-in Post-launch Paper Stage

Paper writing will run as an independently repeatable post-launch stage behind one shared application service. Vegapunk will expose a standalone paper command for historical runs, retries, and resume, while discovery may call the same service after writing its launch summary only when paper generation is explicitly enabled. Paper generation is disabled by default, and a failed Paper Run does not change a successful Discovery Launch outcome. This preserves existing discovery behavior and avoids unexpected model, search, and compilation costs while still supporting an automated end-to-end workflow.

**Considered Options**

- Run paper writing unconditionally after every eligible Discovery Launch. Rejected because it changes existing cost, latency, dependency, and failure behavior without user consent.
- Support only a standalone paper command. Rejected because it would prevent discovery from offering a configured end-to-end closed loop.
