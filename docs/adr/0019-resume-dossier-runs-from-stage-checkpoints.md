---
status: accepted
---

# Resume Dossier Runs from Stage Checkpoints

Remove PaperOrchestra's outer loop that reruns the complete writing pipeline after any exception. Each Dossier Run persists one `dossier_run.json` containing stage status, output paths, and error information; a stage is complete only after its expected output has been validated. Reinvoking the same Dossier Run ID preserves completed outputs and resumes from the first incomplete or failed stage, while an intentionally fresh attempt receives a new Dossier Run ID.

The content-refinement and formatting-correction iteration limits defined in ADR-0018 remain internal to their respective stages. This checkpoint boundary avoids repeated model calls and preserves inspectable intermediate artifacts without treating a resumed execution as a new research result.

**Considered Options**

- Retain PaperOrchestra's complete-pipeline retry loop. Rejected because a late failure repeats successful model work and may replace otherwise valid intermediate outputs.
- Always create a new Dossier Run after failure. Rejected because transient operational failures should be recoverable without abandoning the existing run or duplicating completed stages.
