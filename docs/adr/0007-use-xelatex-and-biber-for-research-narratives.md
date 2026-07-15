---
status: superseded by ADR-0101
---

# Use XeLaTeX and Biber for Papers

Papers will be compiled with XeLaTeX and Biber rather than PaperOrchestra's existing PDFLaTeX and BibTeX sequence. XeLaTeX is required by ElegantPaper's Chinese mode, and Biber is ElegantPaper's default bibliography backend with more reliable Unicode handling for Chinese authors and titles. PaperOrchestra's `references.bib` output remains the direct bibliography input through `\addbibresource{references.bib}`; no bibliography conversion or intermediate representation will be introduced.

**Considered Options**

- Use XeLaTeX with BibTeX to minimize the compiler change. Rejected because the smaller code change would give up Biber's stronger Unicode support and diverge from ElegantPaper's default path.
- Keep PDFLaTeX and BibTeX. Rejected because PDFLaTeX does not satisfy ElegantPaper's Chinese compilation contract.
