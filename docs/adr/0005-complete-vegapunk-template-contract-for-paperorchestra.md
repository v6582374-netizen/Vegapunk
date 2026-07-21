---
status: superseded by ADR-0006
---

# Complete the Vegapunk Template Contract for PaperOrchestra

PaperOrchestra will use Vegapunk's existing `tex_templates/iclr2026/` directory as its default LaTeX template source. The integration will preserve the existing ICLR 2026 resources and add the two entries required by PaperOrchestra: a `template.tex` writing entrypoint initialized from `iclr2026_conference.tex`, and a `guidelines.md` containing explicit ICLR 2026 writing and layout rules. The initial migration will not import PaperOrchestra's older ICLR 2025 template, introduce a template translation layer, or broaden PaperOrchestra's loader to support a differently named entrypoint, because the current mismatch is limited to the directory contract and can be resolved without adding runtime integration logic.

**Considered Options**

- Use PaperOrchestra's bundled ICLR 2025 template unchanged. Rejected because Vegapunk already carries the newer ICLR 2026 resources that should remain authoritative for this project.
- Change PaperOrchestra to accept an arbitrary main TeX filename. Rejected for the initial migration because it expands the imported loader contract to solve a single known filename mismatch.
- Build a runtime adapter that copies or renames template files before each Dossier Run. Rejected because it adds another transformation step without adding information or resolving a semantic incompatibility.
