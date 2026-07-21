---
status: superseded by ADR-0122
---

# Let PaperOrchestra Author Grounded Captions Temporarily

Vegapunk currently requires sci-task agents to save figures and reference them from `report/report.md`, but it does not explicitly require a non-empty Markdown alt text or a separate publication caption, and no Run Report validator enforces either. Until Vegapunk establishes an explicit caption artifact contract, PaperOrchestra may author the publication caption for an eligible Experiment-Sourced Figure.

The caption may use the unchanged figure pixels, its Run Report context, and the Experimental Record. It may explain the figure's subject, encodings, experimental conditions, and already recorded findings, but may not introduce a measurement, numerical value, comparison, interpretation, or claim absent from those artifacts. Existing alt text is optional source context rather than an authoritative caption. The generated caption is stored as a PaperOrchestra output with the figure's Run ID and original relative path; it does not modify the source image or Run Report.

This is an explicit temporary exception, not a reason to treat alt text and caption as the same concept. A later Vegapunk caption contract can replace PaperOrchestra-authored captions without changing ADR-0116's existing-image boundary.
