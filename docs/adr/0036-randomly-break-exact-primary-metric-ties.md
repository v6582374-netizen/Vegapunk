---
status: accepted
---

# Randomly Break Exact Primary-metric Ties

If two or more comparable Candidate Experiments share the exact stored optimal value for the selected primary metric, Terminal Candidate Selection randomly chooses one member of that tied optimum set. The initial integration does not introduce a floating-point tolerance, a secondary metric, or a model-based qualitative tie-break.

The PaperOrchestra Run persists the complete tied set, common value, random tie-break method, and selected candidate before writing begins. Resuming the same Run reuses that selection. The tie and randomized resolution remain Candidate Selection Provenance; ADR-0052 governs whether they are scientifically relevant to the Paper rather than requiring disclosure by default.

**Considered Options**

- Ask a model to choose the more promising method. Rejected because that would add an unrequested subjective scientific ranking after the primary metric produced an objective tie.
- Compare a secondary metric. Deferred because no ordered secondary-metric contract has been accepted for the initial integration.
