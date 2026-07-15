---
status: superseded by ADR-0122
---

# Require InternAgent Experiment Provenance for Every Evidence Figure

PaperOrchestra may synthesize an Explanatory Diagram from the recorded method or system description, provided the diagram is clearly conceptual and carries no unrecorded quantitative result. Every other figure that presents or supports an experimental claim must be an Experiment-Sourced Figure: every datum, sample, panel, curve, comparison, annotation, and quantitative conclusion must originate in the Selected Research Candidate's existing InternAgent Experiment artifacts.

The Plotting Agent may not invent missing observations, interpolate an unrecorded series, manufacture an illustrative result, or use an image model to imitate an experimental visualization. Prompt instructions and model criticism are not sufficient provenance controls. Figure production remains presentation work and cannot become a hidden experiment, metric calculation, statistical analysis, or evidence-repair step.

This decision fixes the scientific source boundary. ADR-0116 subsequently resolves the rendering boundary: PaperOrchestra must reuse an existing Experiment image and may not create a new plot from recorded JSON, CSV, or other structured Experiment values.
