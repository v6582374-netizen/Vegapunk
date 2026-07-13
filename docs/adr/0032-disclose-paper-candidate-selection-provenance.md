---
status: superseded by ADR-0052
---

# Disclose Paper Candidate Selection Provenance

Every Dossier Run records auditable Candidate Selection Provenance. When PaperOrchestra scans backward because one or more later completed Discovery Rounds contain no successful Candidate Experiment, the Research Narrative must state that fallback, identify the skipped round or rounds, and identify the Paper Candidate Round that supplied the selected candidate.

When structured selection metadata is incomplete and a model supplies any comparison criterion, the Research Narrative must explicitly label that criterion as a subjective model judgment rather than a task-defined scientific rule. It must identify the source text used, the inferred criterion, and the candidate values used in the final comparison. If fallback and model judgment both occur, both are disclosed.

These disclosures appear under a candidate-selection subsection of `研究过程` and remain traceable to a structured selection record in the Dossier Run. They may not be omitted by the outline, section-writing, or refinement agents.

**Considered Options**

- Record selection details only in logs. Rejected because a reader of the Research Narrative would not be able to audit why this experiment became the paper's subject.
- Present an inferred criterion as if it came from the task definition. Rejected because it would conceal subjective judgment and overstate the objectivity of the selection.
