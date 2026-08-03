---
status: accepted
---

# Fix Web Discovery to Experiment Mode and Codex

The Web product always starts Discovery in experiment mode and uses the Codex CLI Backend; it does not expose report-only mode or Backend selection. This guarantees that a real Web Launch produces executable Experiment Runs and measured evidence for PaperOrchestra, while following the project's existing Codex-only Discovery Backend decision.

**Considered Options**

- Expose report mode as a Web choice. Rejected because it skips real experiments and cannot provide the measured candidate artifacts expected by the Paper flow.
- Let each researcher choose an Experiment Backend. Rejected because the Web contract would need to support divergent workspace, permission, observability, and failure semantics before the first real path is stable.
