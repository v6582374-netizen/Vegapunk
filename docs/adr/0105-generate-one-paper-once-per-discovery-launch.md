---
status: accepted
---

# Generate One Paper Once per Discovery Launch

Each Discovery Launch automatically invokes PaperOrchestra at most once, after its configured Discovery work reaches Paper Handoff, and owns at most one completed Paper. Provider retries and PaperOrchestra's upstream in-process retry loops remain part of that same Paper generation. Re-entering a Launch after its Paper is complete returns the existing artifacts instead of generating another Paper. Research that should produce a new or expanded Paper must begin as a new Discovery Launch.

The first source-faithful integration does not provide durable PaperOrchestra stage checkpoints or recovery after host or child-process interruption. PaperOrchestra executes as one child-process operation; ordinary failures are reported after the upstream retry policy is exhausted. This deliberately avoids splitting and rewriting the upstream pipeline for a low-probability restart scenario.

This supersedes ADR-0019's stage-checkpoint resume design, ADR-0096's later PaperOrchestra Runs after expanding the same Launch, and ADR-0099's routing back into an unfinished persisted PaperOrchestra Run. Discovery may retain its own core workflow recovery, but Paper Handoff and automatic Paper generation occur only once for a Launch.

**Considered Options**

- Generate another Paper after extending an already handed-off Launch. Rejected because one research effort should own one final Paper; further research intended for publication belongs to a new Launch.
- Add durable stage checkpoints to the vendored pipeline. Rejected because machine or process restart during Paper generation is not common enough to justify broad control-flow changes in the source-faithful port.
