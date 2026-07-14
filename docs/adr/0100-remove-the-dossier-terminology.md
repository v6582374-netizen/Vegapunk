---
status: accepted
---

# Remove the Dossier Terminology

The active domain language is `Research Draft → PaperOrchestra Run → Paper`. The former terms `Research Dossier`, `Research Narrative`, `Dossier Run`, and `Dossier Service` are removed from the current architecture because they came from the abandoned goal of producing a reproducibility dossier or manual and no longer identify distinct concepts.

A PaperOrchestra Run is one resumable PaperOrchestra execution and its workspace. A Paper is that run's publication-oriented TeX, PDF, and figures. This is a terminology simplification only: existing decisions about automatic Draft Handoff, stage checkpoints, preserved prior runs, plotting, refinement, and final outputs remain in force under the new names.

Implementation and active documentation use `paper_orchestra_run` names and a `paper_orchestra_runs/` launch-local directory. Historical ADR filenames and superseded text may retain former words solely as stable records of decisions made before this rename; they do not define current domain concepts.

**Considered Options**

- Retain the old terms as aliases. Rejected because aliases preserve the extra conceptual layer and make the same paper workflow appear to contain different products.
- Rename only the run while retaining Research Dossier and Research Narrative. Rejected because the final output is now simply the Paper rather than a nested view inside another canonical product.
