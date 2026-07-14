---
status: superseded by ADR-0078
---

# Leave Sculptor Multi-Agent Execution to the Backend

InternAgent creates, configures, waits for, and validates one top-level Sculptor Invocation for each Agent Task Completion. It does not implement an editorial Multi-Agent scheduler, define Editorial Subagent roles, assign internal writing tasks, control internal parallelism, or reproduce facilities already provided by an Agent backend such as Claude Code. The Manuscript Sculptor remains free to use the backend's native delegation and Multi-Agent mechanisms when it judges them useful for completing its authoring task.

All native subagents, background agents, and delegated work remain internal to the top-level Sculptor Invocation. Their completion does not create another Agent Task Completion or Sculptor Context Fork, and InternAgent does not observe them as additional manuscript triggers. The Sculptor Completion Barrier is released only when the backend reports that the top-level invocation and its required internal work have finished and the resulting manuscript passes validation.

The backend owns how descendants are created, coordinated, and terminated. InternAgent does not add a separate sandbox, tool whitelist, or child-Agent permission model around this internal execution; the dedicated Manuscript Sculptor Prompt supplies the narrow authoring role while leaving the backend's reasoning and execution strategy free. This avoids coupling the Living Manuscript design to one vendor's Multi-Agent architecture.

**Considered Options**

- Implement project-level Editorial Subagents. Rejected because this duplicates backend-native Multi-Agent architecture and makes InternAgent responsible for internal authoring strategy.
- Disable Agent delegation inside the Sculptor. Rejected because the number of cooperating Agents does not expand the prompt-defined authoring role and should not constrain the backend's reasoning strategy.
- Hook every internal subagent completion. Rejected because it creates recursive Sculptor invocations and leaks backend implementation details into Discovery orchestration.
