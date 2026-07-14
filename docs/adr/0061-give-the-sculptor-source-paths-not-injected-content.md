---
status: superseded by ADR-0078
---

# Give the Sculptor Source Paths, Not Injected Content

Each Manuscript Sculptor invocation identifies the current Living Manuscript by the absolute path of its canonical TeX source. The agent reads that file itself before making an editorial judgment. The invocation similarly supplies paths for the existing `references.bib`, Evidence Carriers, and any large direct artifacts produced by the triggering Research-Significant Action; small stable facts such as the research question, baseline identity, and Terminal Candidate Selection status may remain direct context values.

InternAgent will not serialize the full TeX source into the prompt, create a manuscript summary or snapshot for the agent, or preload the complete Discovery Launch history and logs. This is not an artificial read restriction: the agent may follow references to authoritative source files when needed, but it chooses that context on demand. The canonical files remain the single source of truth instead of competing with prompt copies that can become stale or truncated.

The invocation fails before authoring if the canonical TeX path is missing, resolves ambiguously, or falls outside the active Discovery Launch. It may not reconstruct a manuscript from summaries or silently start a second draft. This refines ADR-0050 and supplies the concrete input contract for ADR-0060's outcome-based judgment.

Under ADR-0062, the same canonical paths are also the authorized output targets rather than read-only prompt references.

ADR-0067 keeps that canonical manuscript source launch-local while it uses the shared repository-local ElegantPaper resources directly.

**Considered Options**

- Inject the complete TeX source into every prompt. Rejected because repeated serialization consumes context, risks truncation, and can diverge from the file being edited.
- Maintain a compact manuscript summary for the writer. Rejected because it becomes another lossy representation that must remain synchronized with the actual paper.
- Preload the whole project history on every invocation. Rejected because access to information does not require forcing all information into the model's active context.
