---
status: accepted
---

# Resume PaperOrchestra Runs from Stage Checkpoints

Remove PaperOrchestra's outer loop that reruns the complete writing pipeline after any exception. Each PaperOrchestra Run persists one `paper_orchestra_run.json` containing stage progress, output paths, and stage-local error information; a stage is complete only after its expected output has been validated. Reinvoking the same PaperOrchestra Run ID preserves completed outputs and resumes from the first incomplete stage, while a later Draft Handoff receives a new Run ID.

The content-refinement and formatting-correction iteration limits defined in ADR-0018 remain internal to their respective stages. This checkpoint boundary avoids repeated model calls and preserves inspectable intermediate artifacts without treating a resumed execution as a new research result.

**Considered Options**

- Retain PaperOrchestra's complete-pipeline retry loop. Rejected because a late failure repeats successful model work and may replace otherwise valid intermediate outputs.
- Always create a new PaperOrchestra Run after an interrupted stage. Rejected because transient operational failures should be recoverable without abandoning the existing run or duplicating completed stages.
