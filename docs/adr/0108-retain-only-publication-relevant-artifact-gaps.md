---
status: superseded by ADR-0110
---

# Retain Only Publication-Relevant Artifact Gaps

The Research Draft exists only to enrich the final Paper where the Discovery Launch's authoritative artifacts are too sparse. Runtime material belongs in the Draft only when it both advances the paper's scientific argument and fills an Artifact Gap. Material already expressed sufficiently by code, reports, metrics, figures, citations, or other artifacts is referenced rather than copied; material with no argumentative value is discarded.

Eligible material includes otherwise-transient research rationale, mechanisms, design trade-offs, result interpretation, error patterns, negative findings, limitations, comparisons, literature synthesis, missing method details, and links between claims and authoritative artifacts. Transport envelopes, prompts, routine logs, progress output, retries, stack traces, duplicated artifact content, and unrelated model or tool output do not qualify merely because they were observable.

This supersedes the exhaustive-retention and no-semantic-filtering parts of ADR-0077, ADR-0078, ADR-0081, ADR-0086, and ADR-0098. It does not yet decide when relevance is evaluated, who performs that evaluation, how retained material is structured, or what size budget applies.

**Considered Options**

- Remove the Research Draft entirely. Rejected because the original project artifacts omit scientifically useful reasoning and interpretation needed for a substantive paper.
- Preserve every observable runtime event and let PaperOrchestra filter it later. Rejected because duplication and operational noise make the material unbounded without adding corresponding writing value.
