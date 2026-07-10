---
status: accepted
---

# Randomly Break Exact Primary-metric Ties

If two or more comparable Candidate Experiments share the exact stored optimal value for the selected primary metric, Terminal Candidate Selection randomly chooses one member of that tied optimum set. The initial integration does not introduce a floating-point tolerance, a secondary metric, or a model-based qualitative tie-break.

The Dossier Run persists the complete tied set, common value, random tie-break method, and selected candidate before writing begins. Resuming the same Dossier Run reuses that selection, and the Research Narrative discloses the tie and randomized resolution through Candidate Selection Provenance.

**Considered Options**

- Ask a model to choose the more promising method. Rejected because that would add an unrequested subjective scientific ranking after the primary metric produced an objective tie.
- Compare a secondary metric. Deferred because no ordered secondary-metric contract has been accepted for the initial integration.
