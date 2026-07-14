---
status: accepted
---

# Define the Observable Research Event Boundary

Draft capture records events exposed at research-runtime seams: Agent lifecycle, model requests and responses, tool calls and results, subprocess execution, Discovery stage or round transitions, and artifact creation or updates. It does not trace operating-system syscalls, scheduler activity, lock contention, or other implementation noise that has no research-facing event contract.

While Discovery capture is active, the existing Python logging, standard-output, and standard-error streams are also mirrored verbatim into individual Draft Blocks while continuing to reach their original console or file destination. The mirror performs no parsing, semantic selection, or labeling and is removed at Draft Handoff, so PaperOrchestra output remains confined to its own run workspace.

The initial implementation retains Claude Code's existing single-result `--output-format json` invocation. It records the complete invocation prompt, subprocess result, standard error, exit outcome, and returned JSON as exposed events, but does not switch to `stream-json` merely to expose Claude Code's internal subagent and tool event stream. That deeper visibility remains an empirical follow-up if real Draft output proves the final-result boundary insufficient.

Capture also does not take before-and-after directory snapshots or copy the complete contents of changed text artifacts into the Draft. Artifact paths and changes that the runtime already reports remain observable events, while the files themselves stay authoritative under the Launch root that Draft Handoff gives PaperOrchestra. This avoids duplicating large code and result trees merely to make the raw record larger.
