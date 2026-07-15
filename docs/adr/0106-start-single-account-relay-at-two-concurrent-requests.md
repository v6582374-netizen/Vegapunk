---
status: accepted
---

# Set Discovery's Hardcoded LLM Concurrency to Two

The current Relay Provider deployment has one account behind the model endpoint, while the Discovery implementation hardcodes ten concurrent LLM tasks in its reflection, evolution, method-development, and refinement phases, and Survey hardcodes the same value for its scoring work. Set those LLM-task limits to 2 for the next run. Survey's external literature-search limit remains 10 because it is not a `/responses` request. This is a source/configuration change made between runs; the process does not adapt the value at runtime, and retry behavior is outside this decision.

**Considered Options**

- Keep the LLM-task limit at 10. Rejected because one-account operation already produces upstream authentication, account-availability, and gateway-timeout failures under that load.
- Change every kind of concurrency, including literature-search concurrency. Rejected because search traffic is a separate external workload and is not the `/responses` burst described by this incident.
- Start at 1. Deferred because 2 is the requested next-test baseline; lowering it later remains a manual source/configuration change.
