---
status: superseded by ADR-0089
---

# Use Three Dossier Run States

`dossier_run.json` uses only three overall states: `running`, `succeeded`, and `failed`. A newly created or interrupted Dossier Run remains `running`; a required-stage error records `failed` together with the error while preserving completed outputs for resume; `succeeded` requires candidate selection, raw-material validation, the complete accepted writing and review loop, final compilation, and existing non-empty final LaTeX and PDF outputs.

Review findings that remain after the accepted content- and layout-correction limits are recorded in a `warnings` collection but do not introduce `partial` or `success_with_warnings` terminal states. A configured PaperOrchestra disable bypasses Dossier creation entirely and therefore does not require a `skipped` Dossier Run.

**Considered Options**

- Add partial and warning terminal states. Rejected because completion and quality observations are separate concerns, and the initial runtime needs an unambiguous resumable lifecycle.
- Mark any unresolved review suggestion as failure. Rejected because the accepted bounded review loop may finish with documented non-blocking recommendations while still producing a valid final narrative.
