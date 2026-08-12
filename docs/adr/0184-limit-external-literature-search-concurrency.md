---
status: accepted
---

# Limit Discovery's External Literature Search Concurrency to Two

Discovery's external literature searches use a separate concurrency budget from
in-process model calls. The previous budget of ten allowed a Survey batch to fan
out ten CrossRef requests at once, which triggered HTTP 429 responses and dropped
those source results. Set the external search budget to two for both Survey and
the orchestration-level evidence phase.

This amends the external-search clause of ADR-0106; the decision to keep model
task concurrency at two remains unchanged.

## Consequences

- CrossRef and other public literature APIs receive a smaller request burst.
- Survey latency may increase because queries complete in more waves.
- A provider may still rate-limit a request; provider-specific backoff and
  `Retry-After` handling remain follow-up work.
- Search concurrency remains independent from Provider-level model concurrency.
