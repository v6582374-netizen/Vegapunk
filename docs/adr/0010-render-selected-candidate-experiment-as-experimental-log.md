---
status: accepted
---

# Render the Selected Candidate Experiment as experimental_log.md

PaperOrchestra's `experimental_log.md` will be a deterministic Markdown rendering of the complete artifact directory belonging to the Selected Research Candidate's Candidate Experiment. The directory is the single authoritative input boundary; its per-run metrics, reports, and failure records remain the sources of truth, while the Markdown file is a read-only view shaped for PaperOrchestra. Rendering may select and arrange explicit file content but may not call a model, infer results, or replace missing measurements.

No existing single file is an adequate substitute. `final_info.json` contains measured metrics but no experiment account, `report/report.md` describes only one Experiment Run, `traceback.log` covers failures, and the backend-specific `experiment_report.txt` is a model-generated summary that is neither universal nor authoritative for numerical claims. The exact run coverage and per-run field projection remain separate input-contract decisions.

The rendering covers `run_0` as the baseline and every subsequent numbered Experiment Run in ascending numeric order. It does not select or infer a best run, hide failed attempts, or reorder attempts by outcome. Iterative runs must be labeled as attempts; they are not described as ablation studies unless the underlying artifacts explicitly identify an ablation design.

Each rendered run contains its identifier, relative artifact path, and a structural status of baseline, successful, failed, or no metrics produced. When present, `final_info.json` is embedded as unchanged JSON and `report/report.md` is embedded verbatim. The renderer does not calculate improvement rates, aggregate scores, or preferred outcomes. Failed runs reference the relative `traceback.log` path without embedding or classifying the stack trace in the initial integration; the complete log remains in the Candidate Experiment directory.

**Considered Options**

- Use only `experiment_report.txt`. Rejected because it is backend-specific, model-generated, and may omit or restate the underlying measurements.
- Use only the final run's `final_info.json`. Rejected because it omits the baseline, earlier attempts, implementation context, and failure evidence required to interpret the result.
