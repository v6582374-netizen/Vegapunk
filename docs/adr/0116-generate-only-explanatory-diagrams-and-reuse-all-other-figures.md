---
status: superseded by ADR-0122
---

# Generate Only Explanatory Diagrams and Reuse All Other Figures

PaperOrchestra may autonomously generate only Explanatory Diagrams: conceptual method, architecture, or process-flow visuals that carry no experimental observation or quantitative result. Every other figure, including statistical plots, curves, scatter plots, qualitative examples, comparisons, and diagnostic images, must already exist as an image artifact produced and persisted by an InternAgent Experiment belonging to the Selected Research Candidate.

PaperOrchestra may select, copy, reference, and place those existing Experiment-Sourced Figures, but it may not reconstruct them from JSON or CSV values, generate replacement Matplotlib code, redraw them, synthesize visually similar results, or modify their pixels. Exact structured Experiment values remain available for paper text and tables under ADR-0113, but not for new figure generation.

This supersedes ADR-0115. It also requires a narrow adaptation to the upstream plotting workflow: the diagram path remains active, while every non-diagram plotting-plan item must resolve to an existing approved Experiment image rather than invoke the upstream model-generated plot renderer.
