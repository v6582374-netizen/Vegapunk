---
status: superseded by ADR-0088
---

# Plan Evidence Carriers with the Scientific Argument

Whenever the Manuscript Sculptor creates or revises the Adaptive Argument Structure, it also decides how each central claim is best supported in the manuscript: by a figure, table, equation, algorithm, prose argument, or a combination. Carrier choice, placement, captioning, and section order are one editorial decision because an overview figure can establish the vocabulary for later sections, a result table can define the comparison being discussed, and a diagnostic plot can determine the order of an explanation. This work happens in the same sculpting pass and does not introduce a separate figure plan, registry, planner agent, or orchestration stage.

InternAgent will not enforce a minimum figure or table count. A theoretical paper may be best organized by definitions and equations, while empirical or diagnostic claims may demand visual or tabular comparison; prose-only support remains valid when it is the clearest form. Final validation checks that central claims have appropriate, referenced, and evidence-traceable carriers rather than checking whether the manuscript contains an arbitrary media quota. ADR-0056 establishes the authoritative source boundary for research-generated carriers, and ADR-0057 governs how the Manuscript Sculptor may render a missing carrier without performing new science.

This refines ADR-0051. The supporting [top-conference sample](../research/top-conference-paper-section-planning.md) found that strong papers plan figures and sections jointly rather than treating visuals as decoration added after drafting.

**Considered Options**

- Write all prose first and add figures afterward. Rejected because late visuals cannot shape the explanatory order and are easily omitted entirely.
- Require a fixed minimum number of figures or tables. Rejected because it rewards decorative output and mismatches theoretical, empirical, diagnostic, and resource contributions.
- Add a separate figure-planning agent or intermediate plan. Rejected because carrier selection is inseparable from the Manuscript Sculptor's existing editorial judgment and another handoff would add synchronization noise.
