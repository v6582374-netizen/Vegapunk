---
status: accepted
---

# Locate PaperOrchestra Runs at the Discovery Launch

Each PaperOrchestra Run uses an independent `paper_orchestra_runs/<paper_orchestra_run_id>/` workspace directly under its Discovery Launch directory. PaperOrchestra treats every InternAgent Candidate Experiment directory as read-only: it may reference and read existing experiment artifacts, but it may not add PaperOrchestra files, move artifacts, rewrite files, or introduce a new manifest there.

The Run workspace contains PaperOrchestra's `working_materials/`, `evidence/`, generated `latex_writeup/`, checkpoint manifest, figures, and final PDF. This supersedes ADR-0014 because the Paper is a launch-level product and its storage must not alter the Candidate Experiment layout while candidate selection remains optional context.

```text
<discovery_launch>/
├── discovery_summary.json
├── session_*/
└── paper_orchestra_runs/
    └── <paper_orchestra_run_id>/
        ├── paper_orchestra_run.json
        ├── working_materials/
        ├── evidence/
        ├── latex_writeup/
        └── final_paper.pdf
```

**Considered Options**

- Add `paper_orchestra_runs/` beneath the selected Candidate Experiment. Rejected because it writes PaperOrchestra-owned state into an InternAgent experiment directory that must remain read-only.
- Use a project-global paper output tree. Rejected because it would separate the Paper from the Discovery Launch whose evidence it explains.
