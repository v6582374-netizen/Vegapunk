Status: accepted

# Use Dual Bounded Retry Budgets

Every Unified Model Runtime request will be constrained by both a maximum attempt count and a maximum elapsed time, with exponential backoff capped by a configured delay.
The initial resilient policy is eight attempts, fifteen minutes of elapsed time, a two-second initial delay, and a sixty-second delay cap; these values are Provider Configuration and may be tuned without changing routing semantics.

## Consequences

- Provider instability can be absorbed without unbounded process hangs.
- All capability operations share one retry mechanism while retaining one Provider, model, and protocol.
- A request that exhausts either budget becomes a terminal error for the owning workflow.
