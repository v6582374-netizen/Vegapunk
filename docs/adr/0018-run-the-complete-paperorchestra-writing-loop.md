---
status: superseded by ADR-0101
---

# Run the Complete PaperOrchestra Writing Loop

After Draft Handoff, the automatically invoked PaperOrchestra loop includes input validation, Draft ingestion, launch-evidence collection, adaptive outline generation, figure generation and visual critique, Introduction and Related Work writing from the fixed citation collection, remaining-section writing, XeLaTeX/Biber compilation, content review and refinement, multimodal layout review, optional layout correction, and final compilation. The Run advances through recorded stage checkpoints and produces the Paper only after the complete writing and reflection loop, not merely an initial draft.

Content refinement runs for at most three iterations and stops with the last accepted compiled version when a new version lowers the overall review score or degrades its review axes. Layout review always runs; when it reports actionable issues, at most one formatting-only correction is attempted, otherwise the compiled content version becomes final. Paper-to-paper side-by-side ratings, Citation F1, and other offline benchmark evaluators are excluded because they do not participate in generating one Paper.

**Considered Options**

- Stop after the first compiled draft. Rejected because it would omit PaperOrchestra's defining content- and layout-reflection stages.
- Run every upstream autorater and benchmark. Rejected because comparison and benchmark utilities add cost and external dependencies without advancing the single-Paper runtime loop.
