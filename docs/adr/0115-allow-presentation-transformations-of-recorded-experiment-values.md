---
status: superseded by ADR-0116
---

# Allow Presentation Transformations of Recorded Experiment Values

An Experiment-Sourced Figure may either reuse an image already produced by an Vegapunk Experiment or be newly rendered from exact structured values recorded in the Selected Research Candidate's Experiment artifacts. The latter is a Presentation Transformation: it may select, order, label, and map recorded values to visual channels, but it may not create a new measurement, metric, aggregation, fit, smoothing operation, interpolation, statistical inference, selection judgment, or repaired value.

Every rendered value must retain machine-auditable provenance to its exact source artifact and structured field. The rendering specification and resulting figure belong to the PaperOrchestra Run and do not modify the Experiment artifacts. This extends ADR-0114 without authorizing model-generated data; the mechanism that prevents a model-authored plot from altering source values remains a separate implementation decision.
