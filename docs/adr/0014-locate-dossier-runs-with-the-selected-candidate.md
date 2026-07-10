---
status: superseded by ADR-0024
---

# Locate Dossier Runs with the Selected Candidate

Each Dossier Run will use an independent `dossier_runs/<dossier_run_id>/` workspace inside the Selected Research Candidate's Candidate Experiment directory. The workspace contains the PaperOrchestra-compatible `raw_materials/`, generated `latex_writeup/`, and final PDF, so retries do not overwrite earlier attempts and the research idea, Experiment Runs, paper inputs, and narrative outputs remain inspectable under one experiment boundary.

The initial integration will not create a separate project-level staging tree or write paper artifacts to the repository root. PaperOrchestra's `raw_materials/` name is retained as its concrete runtime input directory, not promoted into an additional domain abstraction.

**Considered Options**

- Place Dossier Runs in a global output directory. Rejected because it separates the Research Narrative from the Candidate Experiment evidence it explains.
- Reuse one mutable paper workspace per candidate. Rejected because retries would overwrite inputs, intermediate LaTeX, and prior outputs.
