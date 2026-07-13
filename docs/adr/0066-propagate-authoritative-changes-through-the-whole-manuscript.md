---
status: accepted
---

# Propagate Authoritative Changes Through the Whole Manuscript

When newly supplied authoritative information strengthens, weakens, changes, or invalidates an existing conclusion, the Manuscript Sculptor does not complete until every dependent part of the Living Manuscript is consistent with the new account. This includes any affected abstract claims, contribution statements, assumptions, method descriptions, result interpretations, comparisons, limitations, conclusions, citations, equations, tables, figures, and captions. Appending a local correction while leaving the superseded narrative elsewhere is not an acceptable revision.

The Manuscript Sculptor Prompt expresses this as a manuscript-wide outcome constraint, not as a dependency graph, checklist, edit mode, or prescribed traversal. The agent reads the canonical source and determines the semantic impact itself. Deterministic validators continue to handle syntax and reference integrity; semantic propagation remains part of ADR-0060's editorial completion criterion.

This refines ADR-0050, ADR-0060, and ADR-0064.

**Considered Options**

- Add a correction only where the new information arrived. Rejected because abstracts, conclusions, figures, and earlier framing can continue asserting the obsolete account.
- Maintain an explicit claim-dependency graph. Rejected because the capable writing agent can inspect the manuscript directly and another semantic representation would introduce synchronization error.
- Preserve the old interpretation as process history. Rejected unless it has independent scientific value under ADR-0052.
