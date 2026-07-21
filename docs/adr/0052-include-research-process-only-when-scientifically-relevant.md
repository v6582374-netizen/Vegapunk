---
status: accepted
---

# Include Research Process Only When Scientifically Relevant

Vegapunk will not require a `研究过程` section, a chronological account of discovery, or routine workflow provenance in the Paper. A process outcome present in Native Discovery Artifacts enters the Paper only when it performs a necessary scientific function: it supports, tests, falsifies, or qualifies a claim; supplies an ablation or causal explanation; establishes a limitation or boundary condition; or is needed to interpret the method or evaluation. When included, PaperOrchestra places it where it advances the Adaptive Argument Structure rather than collecting it in a process-history container.

Operational chronology, retries, orchestration choices, and Candidate Selection Provenance remain available in their authoritative artifacts but are excluded from the manuscript by default. Auditability does not by itself establish publication relevance. This supersedes ADR-0032 and the mandatory manuscript-disclosure clauses of ADR-0033, ADR-0035, ADR-0036, ADR-0037, and ADR-0039; their requirements to validate and persist Candidate Selection Provenance remain accepted.

**Considered Options**

- Preserve `研究过程` as a mandatory top-level section. Rejected because project chronology consumes argument space without necessarily helping a reviewer assess the scientific contribution.
- Remove all failed attempts and course corrections. Rejected because negative results, ablations, causal evidence, and discovered boundary conditions can be part of the scientific contribution.
- Treat every auditable decision as manuscript content. Rejected because evidence retention and paper composition have different selection criteria.
