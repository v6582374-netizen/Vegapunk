---
status: superseded by ADR-0077
---

# Share ElegantPaper Resources with One Manuscript per Launch

The repository-local `tex_templates/elegantpaper/` directory is a shared, read-only runtime dependency for every Discovery Launch. The writing pipeline uses its `elegantpaper.cls`, setup contract, guidelines, and presentation resources directly rather than copying the directory into each Dossier or manuscript workspace. The project-local upstream import and Chinese-capable template choice from ADR-0006 remain unchanged.

Each Discovery Launch owns exactly one canonical editable TeX source for its Living Manuscript, together with its bibliography and Evidence Carriers. That source resolves the shared ElegantPaper resources through the configured TeX search path or explicit runtime paths; the Manuscript Sculptor never edits the shared `template.tex`, class, examples, or assets. Multiple launches therefore share presentation infrastructure without sharing manuscript state.

Launch initialization deterministically creates `manuscript/main.tex` and `manuscript/references.bib` before the first research Agent task begins. The TeX source is only a minimal compilable document that selects the shared Chinese-capable ElegantPaper class and contains no sections, placeholders, claims, or copied example content; the bibliography starts empty. The first Agent Task Completion therefore has a stable canonical TeX absolute path without asking orchestration to prewrite scientific prose or copying the ElegantPaper directory.

This supersedes only ADR-0006's per-run template-copy and template-rewrite behavior and replaces the current PaperOrchestra `copytree(template_dir, workspace)` workspace setup. It refines ADR-0061 and ADR-0062 without introducing a template registry or another manuscript representation.

**Considered Options**

- Copy the whole ElegantPaper directory into every launch. Rejected because immutable presentation resources need not be duplicated for each manuscript.
- Edit the shared `template.tex` as the Living Manuscript. Rejected because one launch would contaminate every later or concurrent launch and destroy the template/manuscript boundary.
- Ask the first Sculptor Invocation to create a missing manuscript path. Rejected because every Hook should receive the same existing canonical source rather than treating the first invocation as a special bootstrap mode.
- Depend on a globally installed ElegantPaper package. Rejected because the project-local version and provenance must remain reproducible.
