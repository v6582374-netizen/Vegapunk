---
status: accepted
---

# Preserve PaperOrchestra Final Output Names

Each successful Dossier Run exposes `final_paper.pdf` at its root as the single final PDF and retains the final editable source at `latex_writeup/final_refined_paper.tex`. `dossier_run.json` reports these stable relative paths, and the `succeeded` transition validates that both files exist and are non-empty.

Intermediate TeX, PDFs, screenshots, reviews, and compiler artifacts remain under `latex_writeup/` for inspection and reproduction. The integration will not add duplicate aliases such as `paper.pdf` or `research_narrative.pdf`, preserving PaperOrchestra's established output convention.

**Considered Options**

- Rename the PDF to match the Research Narrative domain term. Rejected because the existing unambiguous filename already serves the runtime contract and renaming adds migration churn without new information.
- Copy the final TeX to the Dossier Run root. Rejected because `latex_writeup/` is the complete reproducible LaTeX workspace and already contains the authoritative final source.
