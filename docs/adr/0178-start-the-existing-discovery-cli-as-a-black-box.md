---
status: superseded by ADR-0179
---

# Start the Existing Discovery CLI as a Black Box

The Web backend starts the existing `launch_discovery.py` command as the sole real execution entrypoint. The Web adapter may materialize the task directory, configuration, and output location required by that command, but it does not import, reimplement, or orchestrate `IdeaGenerator`, `ExperimentRunner`, PaperOrchestra, or their internal stages.

**Considered Options**

- Call Discovery internals directly from the Web backend. Rejected because it would create a second orchestration path and allow Web behavior to drift from the production CLI.
- Reimplement only the visible stages in a Web-specific runner. Rejected because the existing launcher already owns the complete automatic workflow and its artifact contract.
