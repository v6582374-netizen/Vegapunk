---
status: superseded by ADR-0078
---

# Require Context-Fork-Capable Agent Runtimes

Living Manuscript execution requires every Agent backend participating in a Discovery Launch to be a Sculptor-Capable Agent Runtime. Before research begins, launch preflight verifies that each configured backend can retain a completed source task's full observable context, create a distinct child or forked invocation from it, inject the dedicated Manuscript Sculptor Prompt with its narrow authoring role, and keep the source task inside the Sculptor Completion Barrier until validation succeeds.

The source backend performs the context fork because it still owns the live conversation or session state. Discovery Launch installs the same Sculptor hook, canonical manuscript path, dedicated prompt, and validation contract into each backend but does not collect, normalize, summarize, or relay the research content itself. Native session fork or continuation is preferred; an exact in-memory clone of the runtime's observable messages and tool events is also valid when it introduces no summarization or selection. A final response, `stdout`, log file, research summary, or artifact path alone is not an equivalent context fork.

Vegapunk creates and awaits only the top-level Sculptor Invocation. ADR-0074 leaves any native Multi-Agent execution within that invocation to the backend that owns it.

For Claude Code, support means capturing the completed source session ID and immediately using the backend's native resume-and-fork facility to start the Sculptor with its dedicated prompt and canonical TeX path. The project does not wrap that direct call in another content-transfer or control protocol.

ADR-0075 requires this capability to execute before the source Agent's task method returns, while that method still owns the complete context needed by the fork.

If any configured backend lacks this capability, a Living Manuscript launch fails during preflight rather than starting with partial coverage or silently degrading to path-first reconstruction. Supporting that backend requires adding an equivalent context-fork implementation; it does not justify weakening the manuscript contract for every other runtime.

**Considered Options**

- Let Discovery Launch reconstruct a common handoff from backend outputs. Rejected because the launch layer does not own the original Agent context and would introduce another normalization boundary.
- Permit a path-only fallback for incompatible backends. Rejected because the same workflow would then provide materially different information fidelity depending on an invisible backend choice.
- Continue the source Agent as the writer. Rejected because context continuity must not erase the Sculptor's separate prompt, restricted authority, or editorial role.
