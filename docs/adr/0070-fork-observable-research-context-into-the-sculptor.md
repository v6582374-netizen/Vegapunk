---
status: superseded by ADR-0078
---

# Fork Observable Research Context into the Sculptor

At every Agent Task Completion, the source runtime will invoke a new Manuscript Sculptor before discarding the source context. The Sculptor Context Fork transfers the exact context observable to the runtime, including source instructions, messages, tool calls, tool results, and direct outputs, without first reducing them to a summary, handoff report, ledger entry, or path-only notification. The runtime then injects the dedicated Manuscript Sculptor Prompt and the absolute canonical TeX path so the new invocation inherits the research context while receiving the Sculptor's deliberately narrower authority and independent editorial objective. Under ADR-0072, the source task remains inside its completion boundary until that invocation has produced a validated manuscript state.

The fork cannot expose or promise hidden model reasoning. Research artifacts remain the authoritative scientific evidence and their paths remain available to the Sculptor for verification, citation, and Evidence Carrier construction, but they are no longer the primary mechanism for reconstructing what the preceding Agent just learned or did. A backend that discards its observable Agent context before invoking the Sculptor does not satisfy this contract merely by forwarding the resulting workspace path.

This supersedes ADR-0061's path-first input contract while preserving its single canonical manuscript and prohibition against prompt copies of the TeX source. It also preserves ADR-0062's direct-file editing boundary: inherited research context expands what the Sculptor can understand, not what files or research decisions it is authorized to change.

ADR-0073 makes this fork a mandatory Agent-runtime capability rather than a best-effort optimization with a path-only fallback.

For a Claude Code source task, the complete core handoff is a native fork of the source session identified by its session ID, followed by injection of the dedicated Manuscript Sculptor Prompt and the canonical TeX absolute path. Vegapunk awaits that top-level invocation and validates its file result; validation diagnostics resume the same Sculptor under ADR-0063. No additional handoff schema, summary, queue, edit mode, permission layer, or project-managed Multi-Agent protocol sits between the two sessions.

ADR-0076 defines the sole non-fork exception: Terminal Candidate Selection is an authoritative system decision that may have no source Agent session, so its exact in-memory result directly triggers the final Sculptor Invocation.

**Considered Options**

- Invoke the Sculptor later with only artifact paths. Rejected because the Sculptor must reconstruct context that the preceding Agent already possessed, creating avoidable information friction.
- Ask the research Agent to write a handoff summary. Rejected because summarization introduces another lossy representation and lets the source Agent preselect what the Sculptor is allowed to notice.
- Continue the research Agent under a writing instruction. Rejected because inherited context should not erase the separate Sculptor role, dedicated prompt, or narrower write authority.
