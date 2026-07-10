---
status: accepted
---

# Use the Discovery Launch as the Dossier Service Input

The single async Dossier Service entrypoint receives a completed Discovery Launch directory, an optional Dossier Run ID, and PaperOrchestra-owned configuration. It does not require `launch_discovery.py` or a historical-run command to identify or pass a Candidate Experiment directory.

From the launch boundary, the service validates `discovery_summary.json`, determines the Paper Candidate Round, performs Terminal Candidate Selection, persists `candidate_selection.json`, links the selected result to its exact Candidate Experiment and full Idea, prepares raw materials, and runs the ported PaperOrchestra pipeline. Existing discovery code therefore adds only one application-service call and never imports or coordinates individual PaperOrchestra agents.

**Considered Options**

- Require the caller to pass a selected Candidate Experiment. Rejected because it leaks candidate-selection logic into discovery or requires a person to locate a generated path.
- Let the service scan the project-global results tree. Rejected because the completed Discovery Launch is the bounded input and prevents accidentally consuming another launch.
