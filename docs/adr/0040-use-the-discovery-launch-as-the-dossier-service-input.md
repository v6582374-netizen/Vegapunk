---
status: superseded by ADR-0110
---

# Use the Discovery Launch as the PaperOrchestra Input

The single async PaperOrchestra entrypoint receives a completed Discovery Launch directory, an optional PaperOrchestra Run ID, and PaperOrchestra-owned configuration. It does not require `launch_discovery.py` or a historical-run command to identify or pass a Candidate Experiment directory.

From the launch boundary, PaperOrchestra validates `discovery_summary.json` and `manuscript/draft.md`, optionally performs Terminal Candidate Selection, ingests the complete Research Draft in bounded batches, gathers launch-wide citations and figures, and runs the writing pipeline. Existing discovery code therefore adds only one call and never imports or coordinates individual PaperOrchestra agents.

**Considered Options**

- Require the caller to pass a selected Candidate Experiment. Rejected because it leaks candidate-selection logic into discovery or requires a person to locate a generated path.
- Let the service scan the project-global results tree. Rejected because the completed Discovery Launch is the bounded input and prevents accidentally consuming another launch.
