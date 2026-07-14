---
status: superseded by ADR-0078
---

# Hold Agent Completion until Sculpting Validates

Every Agent Task Completion enters a synchronous Sculptor Completion Barrier. The source task retains its observable context, waits for exclusive access to the canonical Living Manuscript, invokes the Manuscript Sculptor through the Sculptor Context Fork, and does not return completion to its caller until the resulting files pass deterministic validation. If validation fails, ADR-0063 keeps the same Sculptor invocation active for forward repair before the barrier can be released.

The barrier serializes only top-level Sculptor Invocations and canonical manuscript mutations. Other Agents whose tasks are still executing may continue research concurrently; when they complete, they wait at their own barriers without discarding their source contexts. Each Sculptor therefore reads the latest validated manuscript state and cannot race another Sculptor, overwrite concurrent editorial changes, or require a later reconciliation pass. Internal Multi-Agent work used by one invocation remains inside that barrier under ADR-0074.

This synchronous design deliberately accepts additional task-completion latency. InternAgent will not let source tasks return immediately and place summaries, paths, context snapshots, or writing jobs into an asynchronous queue, because doing so would reintroduce an intermediate representation, crash-recovery protocol, ordering policy, and final queue-drain phase between research and writing.

**Considered Options**

- Run Sculptor invocations concurrently. Rejected because multiple Agents would edit the same canonical manuscript from different starting states.
- Return the source task and process writing asynchronously. Rejected because the source context must then be copied or persisted after its owning task has ended.
- Pause all research while one Sculptor runs. Rejected because exclusive manuscript access does not require a global research lock; unfinished independent Agent tasks can continue safely.
