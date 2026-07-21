---
status: superseded by ADR-0022
---

# Call the Dossier Service Programmatically after Discovery

Expose one async application entrypoint from `vegapunk.paper_orchestra` that receives the concrete Selected Research Candidate directory and Dossier Run identity at runtime. Formal post-launch execution calls this entrypoint programmatically from Vegapunk; it does not require a person to copy a generated experiment path into a CLI, and discovery code does not import individual PaperOrchestra agents.

Project-wide choices such as model configuration, template, and review defaults remain fixed in Vegapunk configuration. The output-directory convention is also fixed, but the concrete Candidate Experiment directory is runtime data because every Discovery Launch creates new launch, session, and candidate directories. An optional thin CLI may call the same application entrypoint only for independently starting or resuming a historical Dossier Run.

**Considered Options**

- Store one concrete experiment path in project configuration. Rejected because it would become stale after the next Discovery Launch and could silently generate a narrative for the wrong candidate.
- Make a standalone CLI the formal integration path. Rejected because the completed discovery workflow already has the generated candidate path and can pass it without manual intervention.
