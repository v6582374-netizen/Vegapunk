---
status: accepted
---

# Use Adaptive Argument Structure

Vegapunk will not impose shared top-level section names or a shared section order on every Paper. ElegantPaper remains the default presentation shell, while PaperOrchestra's outline, writing, and refinement stages choose and revise an Adaptive Argument Structure according to the contribution type, available evidence, and developing scientific argument; empirical-method, diagnostic, theoretical, and data/resource structures are starting points rather than replacement templates. Final validation will assess the required Argument Responsibilities and coherence of the evidence chain rather than an exact `\\section` sequence. Under ADR-0052, research-process material is included only when it serves that scientific argument; under ADR-0053, operational reproduction instructions do not define the Paper's structure; under ADR-0054, evidence boundaries are required without prescribing a Limitations heading; under ADR-0088, Evidence Carriers are planned and generated as part of the paper workflow rather than added after prose is complete.

This supersedes ADR-0008. The supporting sample and analysis are recorded in [the top-conference section-planning research](../research/top-conference-paper-section-planning.md).

**Considered Options**

- Keep the existing fixed eight-section sequence. Rejected because the sampled award papers use materially different structures for theoretical, methodological, diagnostic, and resource contributions.
- Replace the eight sections with a different universal sequence. Rejected because it would preserve the same mismatch under new section names.
- Let the LaTeX template define scientific structure. Rejected because presentation choice must not determine the manuscript's argument.
