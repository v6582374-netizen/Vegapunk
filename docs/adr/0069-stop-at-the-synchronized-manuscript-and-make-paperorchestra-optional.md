---
status: accepted
---

# Stop at the Synchronized Manuscript and Make PaperOrchestra Optional

After experimental work, Terminal Candidate Selection, and the resulting final Manuscript Sculptor invocation have completed, the latest deterministically valid Living Manuscript is the synchronized paper output of the Discovery Launch. All automatic writing processes then stop. Completion requires a compilable manuscript with valid citations and Evidence Carrier references whose content remains faithful to supplied research evidence; it does not require the stylistic, argumentative, or layout polish of a perfect conference submission, and non-fatal imperfections may remain for later improvement.

PaperOrchestra is no longer automatically triggered, awaited, or required for Discovery Launch success. It remains an explicitly invoked optional post-launch path and may later be redesigned as an optimization module for the synchronized manuscript, but that redesign is outside the current Manuscript Sculptor scope. No optimizer continues in the background after normal launch completion.

This supersedes ADR-0022, ADR-0025, ADR-0026, ADR-0027, and ADR-0041, as well as ADR-0050's previous mandatory final PaperOrchestra loop. ADR-0018 now describes behavior only when the optional PaperOrchestra path is deliberately invoked.

**Considered Options**

- Require PaperOrchestra after every Discovery Launch. Rejected because the continuous writer already delivers the synchronized paper and mandatory optimization would extend cost, runtime, and failure surface beyond the current goal.
- Start PaperOrchestra in the background after returning the manuscript. Rejected because normal completion must mean that all automatic processes have stopped.
- Remove PaperOrchestra permanently. Rejected because its review and refinement capabilities may later be useful as an explicit optimization module.
