---
status: superseded by ADR-0088
---

# Let the Manuscript Sculptor Render but Not Analyze Evidence

When an argument needs an Evidence Carrier that does not already exist, the same Manuscript Sculptor may create and execute a deterministic renderer during its sculpting pass. It may parse authoritative artifacts, preserve and reorder recorded values, format tables, plot already recorded observations or metric series, and depict an already established method or system structure. The renderer, exact input paths, and generated output remain together in the Research Dossier so the carrier can be reproduced and traced without adding a separate Plotting Agent, figure-generation stage, or intermediate planning layer.

A Presentation Transformation may not create a new metric, aggregation, statistical test, model fit, smoothing result, measurement, comparison judgment, or repaired value. If the desired carrier requires any such scientific operation, the Manuscript Sculptor omits it or selects another carrier supported by the available evidence; it does not initiate or request research. If discovery orchestration independently produces the needed result through its own research logic, the resulting Agent Task Completion lets the sculptor reconsider the manuscript.

Deterministic validation checks that the renderer reads only declared authoritative inputs, produces the referenced carrier, and does not alter the Candidate Experiment. This extends ADR-0056 without changing ADR-0050's authority boundary.

**Considered Options**

- Restore a separate Plotting Agent. Rejected because carrier generation is part of the same editorial decision and another agent would reintroduce a lossy handoff.
- Allow the Manuscript Sculptor to compute whatever a desired plot requires. Rejected because presentation choices would then silently become unreviewed scientific analysis.
- Forbid the paper workflow from creating any carrier. Rejected because recorded evidence often exists in a scientifically complete but publication-unusable representation.
