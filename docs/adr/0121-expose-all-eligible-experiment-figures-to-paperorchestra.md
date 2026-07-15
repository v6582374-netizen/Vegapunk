---
status: superseded by ADR-0122
---

# Expose All Eligible Experiment Figures to PaperOrchestra

The Paper Input Bundle exposes every eligible Experiment-Sourced Figure from every Complete Experiment Run belonging to the Selected Research Candidate. The adapter applies only the established provenance, Run-completeness, report-reference, path-boundary, and file-validity checks; it must not filter figures by latest Run, inferred best Run, metric outcome, filename, or guessed publication relevance.

PaperOrchestra's Outline and writing stages choose the subset actually used by the Paper according to the scientific argument. Availability in the Figure Catalog does not require inclusion, and selecting a figure does not authorize pixel modification or new experimental interpretation. The selected subset, generated Figure Captions, Run IDs, and original relative paths are persisted with the PaperOrchestra Run so the editorial choice remains auditable.

The adapter does not deduplicate Catalog entries by content hash, perceptual similarity, or model judgment. If equivalent images are referenced from multiple Complete Experiment Runs, their distinct source entries remain available and PaperOrchestra handles that editorial redundancy during figure selection.
