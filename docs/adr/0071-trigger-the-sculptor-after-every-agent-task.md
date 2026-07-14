---
status: superseded by ADR-0078
---

# Trigger the Sculptor after Every Agent Task

Every Agent Task Completion within a Discovery Launch invokes the Manuscript Sculptor through a Sculptor Context Fork. Discovery orchestration, the source Agent, and trigger infrastructure do not first classify the result by scientific importance, predicted manuscript value, action type, or expected edit scope. The Manuscript Sculptor has broad freedom to determine whether anything is worth adding, removing, revising, or reorganizing and may legitimately leave the Living Manuscript unchanged; that editorial judgment is the reason to invoke it, not a condition for invoking it.

Agent Task Completion is deliberately finer-grained than idea generation, experiment execution, round completion, or other named Discovery stages. It occurs whenever an Agent reaches the final success or exhausted final failure of one bounded assigned task and returns its coherent result or terminal failure context to its caller. Model responses, tool calls, intermediate errors, retries, streaming fragments, and incidental implementation operations inside an unfinished task do not separately trigger the Sculptor because they have not yet formed an independently interpretable terminal outcome, not because orchestration has judged them unimportant.

Success and final failure use the same Hook and leave manuscript relevance to the Sculptor. A scientifically meaningful negative result may change the paper; an infrastructure failure, exhausted technical repair, or irrelevant error may legitimately produce no manuscript edit. Discovery orchestration does not classify those cases before invoking the Sculptor.

This refines ADR-0050 and ADR-0070 by moving manuscript-consideration coverage from a few stage boundaries into every Agent runtime while preserving one Sculptor role, one canonical Living Manuscript, and serialized direct edits. It replaces the `Research-Significant Action` trigger because that term incorrectly let upstream orchestration decide which completed work deserved the Sculptor's attention.

ADR-0072 makes each trigger a synchronous completion barrier so the source context cannot disappear and concurrent Agent completions cannot edit the manuscript simultaneously.

ADR-0073 requires every Agent backend participating in the Discovery Launch to implement the trigger with a genuine context fork.

An Agent Task Completion belongs to the Discovery research orchestration. Under ADR-0074, internal Agents or delegated tasks created inside a Sculptor Invocation remain backend implementation details and do not recursively trigger another Sculptor.

ADR-0075 places the trigger at each research Agent's task-method exit rather than at named Discovery stage or round boundaries.

**Considered Options**

- Trigger only after major Discovery stages. Rejected because the Sculptor must reconstruct or overlook information already available inside smaller research tasks.
- Trigger only when orchestration predicts manuscript impact. Rejected because determining manuscript relevance and edit scope belongs to the Sculptor.
- Trigger after every model or tool operation. Rejected because an unfinished task has no stable result to hand off and would repeatedly fork partial context rather than broaden editorial awareness.
- Trigger only successful Agent tasks. Rejected because a terminal failure can contain a valid negative result, boundary condition, or explanation that the Sculptor should be free to assess.
