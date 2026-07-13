---
status: accepted
---

# Hook Agent Task Exits, Not Discovery Stages

The Sculptor Hook is embedded at the exit of every research Agent task method, after the task has formed its coherent success result or exhausted final-failure context but before that terminal outcome is returned to its caller. MAS research roles trigger from their `execute()` task boundary; Claude Code research tasks trigger from their `run()` boundary after capturing the source session ID. The still-active source runtime performs the Sculptor Context Fork, awaits the Sculptor Completion Barrier, and only then returns the original task outcome. Intermediate exceptions handled by the task's own retry or repair loop do not reach this exit and do not trigger separately.

Discovery stages, rounds, candidate batches, and `launch_discovery.py` do not reconstruct or relay those task contexts and are not the ordinary writing trigger. They may create the Living Manuscript before research begins and perform launch-level terminal duties, but writing coverage comes from the Agent task exits inside them. Concurrent per-idea calls therefore trigger individually when their own Agent tasks finish instead of collapsing several outcomes into one later stage-level handoff.

ADR-0076 makes Terminal Candidate Selection the only explicit launch-level Sculptor trigger because that authoritative decision can be produced without any Agent task to hook.

This is the concrete integration point for ADR-0071 and ADR-0073. It keeps the Hook close to the runtime that owns the context without introducing a generic event bus, result envelope, stage callback registry, or post-stage scan.

**Considered Options**

- Trigger from `launch_discovery.py` after named stages. Rejected because the source Agent context has already been reduced to returned values and artifacts.
- Trigger once after a parallel batch completes. Rejected because individually completed Agent tasks would be merged into a coarser handoff and lose their direct context forks.
- Let stages inspect results and decide whether to trigger. Rejected because manuscript relevance belongs to the Manuscript Sculptor, not stage orchestration.
