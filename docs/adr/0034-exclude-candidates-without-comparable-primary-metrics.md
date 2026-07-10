---
status: superseded by ADR-0037
---

# Exclude Candidates without Comparable Primary Metrics

Provisionally, after Terminal Candidate Selection has established a primary metric, a successful Candidate Experiment whose corresponding value is absent, non-numeric, NaN, or infinite is excluded from the comparable candidate set. PaperOrchestra does not invent a value or treat missingness as better or worse; it records the candidate, missing field, and exclusion reason in Candidate Selection Provenance and discloses the exclusion in the Research Narrative.

If comparable candidates remain, selection continues among them, and a sole remaining comparable candidate is selected directly. The behavior when no comparable candidate remains is not decided by this proposal.
