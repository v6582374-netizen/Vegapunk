---
status: superseded by ADR-0077
---

# Keep the Early Manuscript Sparse Rather Than Speculative

During early research, the Living Manuscript contains only material supported by the authoritative information supplied so far. It may be short, omit conventional sections, and leave some Argument Responsibilities unfulfilled until relevant evidence exists. The Manuscript Sculptor Prompt forbids empty headings, `TBD` prose, promised future results, predicted findings, generic background added for length, and other devices that make an immature manuscript appear complete.

The minimal compileable source created under ADR-0067 is an empty document container, not a prewritten outline. It contains no empty scientific headings for later Agents to fill and imposes no argument structure on the first Sculptor Invocation.

Rhetorical incompleteness does not permit document corruption: the canonical TeX source, bibliography, and referenced Evidence Carriers must still satisfy deterministic validation after every sculpting invocation. As Agent Task Completions supply real material, the same role grows or restructures the manuscript directly; it does not preserve an early empty skeleton merely because headings were created in advance.

This refines ADR-0051, ADR-0060, and ADR-0064. At finalization, missing evidence narrows the paper's claims and contribution rather than licensing the sculptor to invent the absent support.

**Considered Options**

- Pre-create a complete paper outline with empty sections. Rejected because headings anchor later writing to a structure chosen before the contribution is known.
- Fill missing sections with plausible prose. Rejected because apparent completeness would conceal missing scientific support.
- Delay all writing until enough evidence exists for a complete paper. Rejected because it restores the terminal information-loss boundary that the Living Manuscript is intended to remove.
