---
status: accepted
---

# Remove Research Draft Capture

The append-only `ResearchDraft` capture mechanism is removed from the runtime. Vegapunk no longer creates a launch-local `manuscript/draft.md`, intercepts process streams or root logging for that purpose, or records model and tool activity through a draft-specific hook. Agent construction, model execution, tool loops, and the Codex experiment backend therefore have no dependency on the former capture layer.

Discovery and PaperOrchestra continue to use the native, bounded artifacts defined by ADR-0110 and ADR-0113: prompts, candidate records, experiment narratives, exact Run artifacts, logs, and deterministic `raw_materials/` projections. The earlier Research Draft ADRs remain in the repository as superseded historical decisions; they are no longer runtime contracts.
