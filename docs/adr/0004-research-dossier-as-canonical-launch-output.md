---
status: accepted
---

# Research Dossier as Canonical Launch Output

InternAgent will treat a Research Dossier, rather than a standalone submission-oriented manuscript, as the canonical final product of a Discovery Launch. The dossier combines authoritative structured evidence with a self-explaining LaTeX/PDF Research Narrative that selectively reconstructs the method, results, decision history, failed attempts, course corrections, and reproduction path. Code, manifests, configurations, logs, and measured outputs remain the sources of truth and are referenced through stable identities and integrity metadata instead of being copied wholesale or silently rewritten into the narrative. This refines the `Final Paper` and `Paper Run` terminology used in ADR-0001 and ADR-0002; their one-output, candidate-selection, opt-in execution, and failure-isolation decisions remain in force for the Research Dossier and Dossier Run.

**Considered Options**

- Make the generated PDF/LaTeX manuscript the only authoritative artifact. Rejected because a prose document is a lossy representation of executable inputs, histories, and evidence.
- Add process details as appendices to a conventional submission-oriented paper. Rejected because self-explanation, auditability, and reproducibility are primary product goals rather than supplementary material.
- Insert all available raw context into the narrative. Rejected because indiscriminate inclusion reduces signal, exceeds useful writing context, and increases the chance of unsupported synthesis.
