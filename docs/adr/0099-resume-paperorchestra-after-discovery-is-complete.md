---
status: superseded by ADR-0105
---

# Resume PaperOrchestra After Discovery Is Complete

Resuming a Discovery Launch does not exit merely because every currently configured Discovery round is already complete. If that Launch's latest Draft Handoff has an unfinished PaperOrchestra Run, the normal launch entrypoint skips Discovery work and resumes PaperOrchestra from that run's existing stage checkpoints. If the latest run already contains the completed paper artifacts, the entrypoint returns those artifacts without regenerating them.

When the resumed invocation actually performs additional configured Discovery work, it appends to the Research Draft and creates a new PaperOrchestra Run at the later handoff under ADR-0096. The earlier run is not reused against the expanded Draft.

This behavior adds no Draft checkpoint and no second resume mechanism. Discovery and PaperOrchestra retain their own core checkpoints; the launch entrypoint only routes control to the part of the workflow that still has work to continue.

**Considered Options**

- Return immediately whenever Discovery has no remaining rounds. Rejected because an interrupted PaperOrchestra run would become unreachable from the normal resume command.
- Restart PaperOrchestra from the beginning. Rejected because its persisted intermediate outputs and stage checkpoints already identify the continuation point.
- Create a new PaperOrchestra Run whenever the resume command is invoked. Rejected because invoking resume without new Discovery information must continue the same paper-generation attempt.
