---
status: accepted
---

# Preserve PaperOrchestra Final Output Names

Each completed PaperOrchestra Run exposes `final_paper.pdf` at its root as the single final PDF and retains the final editable source at `latex_writeup/final_refined_paper.tex`. `paper_orchestra_run.json` reports these stable relative paths, and final-output validation checks that both files exist, are non-empty, and match the recorded hashes.

Intermediate TeX, PDFs, screenshots, reviews, and compiler artifacts remain under `latex_writeup/` for inspection and reproduction. The integration will not add duplicate aliases such as `paper.pdf` or `research_narrative.pdf`, preserving PaperOrchestra's established output convention.

**Considered Options**

- Rename the PDF to another domain term. Rejected because the existing unambiguous filename already serves the runtime contract and renaming adds migration churn without new information.
- Copy the final TeX to the PaperOrchestra Run root. Rejected because `latex_writeup/` is the complete reproducible LaTeX workspace and already contains the authoritative final source.
