---
status: accepted
---

# Use primary as the Automatic Dossier Run ID

The automatic post-discovery trigger uses `primary` as the default Dossier Run ID, producing `<discovery_launch>/dossier_runs/primary/` without requiring a CLI argument or another value stored by `launch_discovery.py`. If `primary` is incomplete, the Dossier Service resumes it; if it has already succeeded, the service returns its existing result without repeating selection, model calls, or compilation.

An intentionally fresh paper-generation attempt must use a different explicit Dossier Run ID and receives an independent workspace, candidate selection, checkpoints, LaTeX, reviews, and PDF. It never overwrites `primary` or another prior Dossier Run.

**Considered Options**

- Generate a new timestamp ID on every automatic invocation. Rejected because resuming the same Discovery Launch could create multiple abandoned writing attempts instead of continuing the interrupted one.
- Store the generated ID in existing InternAgent state. Rejected because a stable launch-local ID removes that additional integration change.
