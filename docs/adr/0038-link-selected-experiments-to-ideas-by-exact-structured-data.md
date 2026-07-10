---
status: accepted
---

# Link Selected Experiments to Ideas by Exact Structured Data

After Terminal Candidate Selection, PaperOrchestra locates the Candidate Experiment from the selected result's recorded `folder_name` in `discovery_summary.json`; it does not reconstruct the path from timestamps or directory names. The containing round's recorded `session_id` identifies the existing session-level `ideas.json` and `traj.json`.

PaperOrchestra matches the selected result's `idea_name` exactly to one executed method in `ideas.json`, then matches that complete `refined_method_details` object exactly to one Idea identified by `traj.json.top_ideas`. The unique full Idea supplies the hypothesis, rationale, baseline context, evidence, references, and method lineage required by the accepted raw-material renderers.

This evidence join may not use fuzzy names, title similarity, a model, or random fallback. If any required file is missing or either structured match is absent or non-unique, Dossier input validation fails before writing because attaching another Idea's evidence or citations would corrupt the scientific subject.

**Considered Options**

- Parse the timestamped Candidate Experiment directory name to recover the method. Rejected because the exact result path and structured method records already exist.
- Randomly choose among ambiguous Idea matches. Rejected because random candidate selection cannot authorize random evidence attribution.
