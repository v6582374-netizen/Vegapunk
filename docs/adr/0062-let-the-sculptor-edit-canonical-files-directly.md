---
status: superseded by ADR-0078
---

# Let the Sculptor Edit Canonical Files Directly

The Manuscript Sculptor edits the canonical TeX source, `references.bib`, Evidence Carriers, and permitted presentation-rendering files directly through its filesystem tools. The resulting file state is the authoritative output of the invocation. The model does not return a complete LaTeX document, structured patch, edit plan, or prose payload for the orchestration layer to parse and write on its behalf.

Any textual agent response is non-authoritative execution status only. Discovery orchestration serializes invocations and runs deterministic validation against the files themselves; it does not interpret the response to reconstruct editorial intent. Under ADR-0063, validation errors return to the same active sculptor for forward repair rather than causing rollback. The sculptor's write scope remains confined to the Living Manuscript area of the active Discovery Launch and may not modify the Candidate Experiment or other authoritative research artifacts.

This refines ADR-0050 and completes ADR-0061's path-based contract. It removes the lossy `model output -> parser -> file writer` boundary used by the one-shot Section Writer without adding a replacement representation between the agent and the manuscript.

**Considered Options**

- Return a complete LaTeX document for the orchestrator to save. Rejected because the returned copy competes with the canonical file and requires another parsing and write boundary.
- Return a structured patch or edit plan. Rejected because the filesystem already records the exact changes and another representation can diverge from the actual edit.
- Allow edits throughout the Discovery Launch. Rejected because editorial authority does not include changing research evidence or experiment outcomes.
