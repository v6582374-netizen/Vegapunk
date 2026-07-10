---
status: accepted
---

# Locate Dossier Runs at the Discovery Launch

Each Dossier Run will use an independent `dossier_runs/<dossier_run_id>/` workspace directly under its Discovery Launch directory. PaperOrchestra treats every InternAgent Candidate Experiment directory as read-only: it may reference and read existing experiment artifacts, but it may not add Dossier files, move artifacts, rewrite files, or introduce a new manifest there.

The launch-level workspace contains PaperOrchestra's `raw_materials/`, generated `latex_writeup/`, checkpoint manifest, and final PDF. This supersedes ADR-0014 because a Research Dossier is the launch-level final product, and its storage must not alter the Candidate Experiment layout while paper-candidate selection remains an independent concern.

```text
<discovery_launch>/
├── discovery_summary.json
├── session_*/
└── dossier_runs/
    └── <dossier_run_id>/
        ├── dossier_run.json
        ├── raw_materials/
        ├── latex_writeup/
        └── final_paper.pdf
```

**Considered Options**

- Add `dossier_runs/` beneath the selected Candidate Experiment. Rejected because it writes PaperOrchestra-owned state into an InternAgent experiment directory that must remain read-only.
- Use a project-global paper output tree. Rejected because it would separate the Research Dossier from the Discovery Launch whose evidence it explains.
