---
status: superseded by ADR-0101
---

# Port PaperOrchestra Core as an Internal Package

The PaperOrchestra runtime required for one Paper will be ported into `vegapunk.paper_orchestra` as an ordinary, internally maintained Python package. The package preserves the Outline, plotting, literature-writing, section-writing, review, content-refinement, format-review, and PDF-review agent architecture together with their prompts, parsing, data types, autoraters, and required utilities. A single pipeline entrypoint is its public interface; existing Vegapunk discovery code does not import or coordinate individual PaperOrchestra agents.

The port excludes the Streamlit frontend, batch and benchmark drivers, legacy shell and CLI entrypoints, bundled venue templates, and online literature-search implementation. ADR-0088 restores the Plotting Agent and ADR-0097 adds its independent image-generation path. The package retains the upstream license and an `UPSTREAM.md` recording the source commit and local adaptations.

**Considered Options**

- Copy the complete repository file for file. Rejected because it would retain unrelated user interfaces, entrypoints, templates, and disabled capabilities without increasing the completeness of the accepted runtime path.
- Reimplement the writing loop directly in existing Vegapunk modules. Rejected because it would discard PaperOrchestra's agent separation and spread migration changes across the discovery codebase.
