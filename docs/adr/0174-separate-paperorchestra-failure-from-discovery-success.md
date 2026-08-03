---
status: accepted
---

# Separate PaperOrchestra Failure from Discovery Success

When a Web Discovery Launch completes its configured Discovery work but its automatic PaperOrchestra Run fails, the product preserves the successful Discovery outcome and reports the Paper failure as a separate terminal result on the same Launch. This keeps valid experiments and Discovery artifacts available, matches the existing production behavior that records PaperOrchestra errors without discarding Discovery output, and avoids turning a downstream writing failure into a false statement that the research execution failed.

**Considered Options**

- Mark the entire Launch failed. Rejected because the Discovery evidence remains valid and independently reviewable.
- Retry PaperOrchestra automatically. Rejected because one Launch owns at most one automatic PaperOrchestra Run; a new research effort should use a new Launch rather than silently changing its provenance.
