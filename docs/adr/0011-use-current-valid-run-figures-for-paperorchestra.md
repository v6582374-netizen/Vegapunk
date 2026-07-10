---
status: accepted
---

# Use Current Valid Run Figures for PaperOrchestra

The initial integration will populate PaperOrchestra's `figures/` input only from `report/images/` of the Selected Candidate Experiment's current valid Experiment Run. Current valid means the highest-numbered run with a non-empty, readable `final_info.json`, matching InternAgent's existing `current_metrics` lookup. It must not be labeled or interpreted as the best run. Figures from the baseline, earlier attempts, failed runs, and unmeasured later runs remain in the Candidate Experiment but are not offered to PaperOrchestra in the first runnable path.

This narrow source prevents PaperOrchestra's current instruction to use every listed figure from forcing outdated, duplicate, or failed-attempt images into the Research Narrative. A deterministic Markdown parser will build `figures/info.json` only from image references explicitly present in the current run's `report/report.md` whose target files exist under `report/images/`. Each entry preserves the original filename and uses the Markdown alt text verbatim as its caption, falling back to the filename when the alt text is empty. Unreferenced image files are not listed, and no model or vision analysis is used to create figure metadata.

The first runnable path will use PaperOrchestra's existing-figure writer and will not invoke its Plotting Agent or image-generation model. If the current valid run has no referenced figures, the integration writes an empty `figures/info.json` array and continues with text and tables; an image-free Candidate Experiment is not a Dossier Run failure. PDF rendering and later page-level layout review remain independent downstream checks.

**Considered Options**

- Offer figures from every Experiment Run. Rejected because PaperOrchestra currently requires every listed figure to appear in the paper, which would mix current evidence with superseded and failed attempts.
- Infer a best run and use its figures. Rejected because the Candidate Experiment does not expose a uniform authoritative best-run marker across backends.
- Generate replacement figures with PaperOrchestra when no experiment figures exist. Rejected from the initial path because generated illustrations would not be direct Experiment Run artifacts and are unnecessary for proving the writing pipeline can complete.
