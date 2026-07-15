---
status: accepted
---

# Use Only Native Discovery Artifacts for the Initial Paper Baseline

The initial source-faithful PaperOrchestra integration constructs its Paper Input Bundle solely from Native Discovery Artifacts that exist independently of paper generation: task and candidate prompts, selected method records, experiment reports, exact metric files, logs, citations, and figures. It neither creates nor consumes `manuscript/draft.md` for paper generation and performs no model-based extraction, summarization, or curation before the vendored PaperOrchestra pipeline. The required upstream `idea_sparse.md` and `experimental_log.md` are deterministic projections of those source artifacts. Source code and `code_summary.json` remain in the Discovery Launch as implementation evidence but are excluded from the initial Paper Input Bundle. Figures are left to the upstream autonomous Plotting Agent under ADR-0122.

This is a control-variable baseline, not a permanent judgment that a Research Draft can never improve paper quality. Paper quality must first be evaluated after replacing the rewritten PaperOrchestra implementation while holding its inputs to the system's natural outputs. Reintroducing any paper-specific capture or model-preparation stage requires a later explicit decision based on that baseline. A Selected Research Candidate remains preferred but non-blocking, and the one-Paper-per-Launch lifecycle in ADR-0105 remains in force.

This supersedes the active Research Draft architecture in ADR-0077, ADR-0078, ADR-0079, ADR-0081 through ADR-0087, ADR-0090 through ADR-0094, ADR-0098, ADR-0100, ADR-0108, and ADR-0109. The former Dossier terminology remains retired; the active flow is Native Discovery Artifacts to Paper Input Bundle to PaperOrchestra Run to Paper.

**Considered Options**

- Add a model step that converts the Research Draft into upstream raw materials. Rejected for the initial baseline because it changes another major variable before the vendored pipeline's own quality has been measured.
- Pass the Research Draft through verbatim. Rejected for the initial baseline because it is a paper-specific mechanism rather than a natural Discovery output and does not match the upstream semantic split between idea and experimental log.
- Include final source code or a derived code diff. Deferred because the first quality baseline should use only the existing human-readable method and experiment artifacts without adding code-selection rules.
