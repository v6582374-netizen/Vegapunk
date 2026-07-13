---
status: superseded by ADR-0051
---

# Fix Research Narrative Top-level Sections

Every Research Narrative will use a fixed set of top-level sections, while the outline and writing agents may create subsections that reflect the selected research candidate. PaperOrchestra already treats the section commands in `template.tex` as its primary skeleton and assumes stable locations for literature review and conclusion work. Keeping the top level stable makes narratives comparable and reviewable across Discovery Launches and provides an explicit structural basis for adding selectable LaTeX templates later.

All Research Narrative Templates will implement the same top-level content contract and section order. A template may change the document class, typography, title treatment, page furniture, dimensions, colors, and bibliography presentation, but it may not add, remove, or redefine the semantic responsibilities of top-level sections. Localized templates may translate displayed section names without changing those responsibilities.

The mandatory scientific core consists of `引言` (Introduction), `相关工作` (Related Work), `方法` (Method), `实验` (Experiments), and `结论` (Conclusion), which must occur in that relative order even if later self-explanation sections are inserted between them. The abstract is mandatory front matter rather than a top-level section. These sections retain PaperOrchestra's existing scientific writing flow; they are the minimum core, not the complete Research Narrative structure.

`研究过程` (Research Process) is a mandatory top-level self-explanation section placed after `实验` and before `结论`. `实验` presents the experimental design and results systematically; `研究过程` explains how the research progressed to those results without scattering that responsibility across the method and experiment sections. Its evidence inputs and missing-information behavior remain separate contract decisions.

Failed attempts and course corrections are optional subsections of `研究过程`, not separate top-level sections. They are generated only when corresponding records exist; an absent record results in an omitted subsection rather than an empty heading or reconstructed process. This preserves useful negative results without making every Research Narrative claim a failure history that may not exist.

`复现指南` (Reproduction Guide) is a mandatory top-level section placed after `研究过程` and before `结论`. It gives the reader an explicit path from environment, inputs, and configuration through execution and result verification instead of treating reproducibility as optional appendix material. Its authoritative inputs and exact content remain separate contract decisions.

`局限性与适用边界` (Limitations and Applicability) is a mandatory top-level section placed after `复现指南` and before `结论`. It states only evidence-supported limits, evaluated conditions, and explicitly untested boundaries. Missing evidence must be reported as unknown or not evaluated rather than replaced by speculative limitations.

**Considered Options**

- Let the outline agent design all section levels independently for every Dossier Run. Rejected because document completeness and downstream agent behavior would vary between runs.
- Let each selectable template define its own top-level content structure. Rejected because changing presentation would then change what PaperOrchestra is asked to explain and make Research Narratives incomparable across templates.
