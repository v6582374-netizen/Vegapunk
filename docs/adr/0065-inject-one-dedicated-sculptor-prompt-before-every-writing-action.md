---
status: accepted
---

# Inject One Dedicated Sculptor Prompt Before Every Writing Action

The Manuscript Sculptor is governed by one dedicated prompt that the runtime injects before every writing action. It is not a reusable skill, does not depend on model- or user-invocation, and is not available to unrelated agents. Every sculpting action therefore receives the same editorial objective, authority boundary, writing principles, and completion conditions without relying on the agent to discover or elect to load them.

The prompt remains a single source of truth rather than being reassembled from action-specific fragments. Runtime context supplies the Sculptor Context Fork, canonical paths, and stable launch facts under ADR-0070; the dedicated prompt supplies role behavior and does not duplicate manuscript content or research artifacts. Its constraints preserve high intellectual and operational freedom: they define the Sculptor's narrow authoring responsibility and prohibitions without replacing the model's editorial judgment with edit modes, a procedural state machine, a project-specific tool whitelist, or a separate runtime sandbox.

ADR-0073 requires every participating Agent backend to preserve this separate prompt and role while forking the source context; continuing the source Agent under its original authority is not an equivalent implementation.

ADR-0074 leaves any internal Multi-Agent decomposition of that prompted Sculptor Invocation to the selected backend rather than defining project-level editorial subagents.

This corrects the `skill` terminology in ADR-0060 and ADR-0064 while preserving their accepted behavior.

**Considered Options**

- Package the behavior as a reusable skill. Rejected because the prompt belongs exclusively to one runtime role and must never depend on optional invocation.
- Assemble a different prompt for each trigger type. Rejected because duplicated fragments would drift and make the sculptor's behavior depend on which research action invoked it.
- Put the entire manuscript and evidence inside the dedicated prompt. Rejected because role constraints and per-action context have different lifetimes and ADR-0061 already defines path-based access.
