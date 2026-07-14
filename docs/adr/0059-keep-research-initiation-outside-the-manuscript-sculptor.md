---
status: superseded by ADR-0078
---

# Keep Research Initiation Outside the Manuscript Sculptor

The research-to-writing boundary is strictly one-way: every Agent Task Completion supplies its Sculptor Context Fork and authoritative outcomes to the Manuscript Sculptor, and the sculptor decides whether the Living Manuscript should change. It cannot initiate, schedule, request, or recommend a literature search, experiment, measurement, statistical analysis, metadata-enrichment task, or any other research action. In particular, discovering sparse citations does not authorize it to call ScholarAgent or send work back to discovery orchestration.

When supplied information is insufficient, the Manuscript Sculptor may only keep the manuscript faithful to what exists: omit an unsupported claim, citation, or Evidence Carrier; narrow or qualify prose when the available evidence supports the narrower statement; remove obsolete material; or make no change. It may not fill the gap by inference or turn it into a reverse orchestration edge. The research module independently owns research completeness and must improve its own triggers and quality criteria rather than relying on the writer to diagnose or repair its output.

This is a role boundary enforced by the mandatory Manuscript Sculptor Prompt, not a project-specific tool sandbox. The Sculptor retains the selected backend's normal execution and Multi-Agent capabilities, but its instructions forbid using those capabilities to initiate research, alter authoritative evidence, or expand its own scientific authority.

This refines ADR-0050's authority boundary, governs citation handling under ADR-0058, and supersedes ADR-0057's earlier feedback path from missing carriers to discovery. Presentation Transformations from already supplied evidence remain permitted.

**Considered Options**

- Let the Manuscript Sculptor search directly. Rejected because editorial authority would silently expand into evidence acquisition and validation.
- Let the Manuscript Sculptor submit research requests without executing them. Rejected because indirect initiation still couples research progression to writing judgments and creates a reverse control edge.
- Let the Manuscript Sculptor retain unsupported material as a placeholder. Rejected because an evolving manuscript must remain evidence-faithful at every accepted revision.
