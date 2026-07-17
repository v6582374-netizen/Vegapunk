Status: superseded by ADR-0145

# Centralize Model Request Retries

The Unified Model Runtime will own bounded retries for transient model-request failures and will never change the Provider, Canonical Model Identity, or declared protocol while retrying.
Consumer-level retry loops and Provider fallback helpers are removed; authentication, validation, capability, and content errors fail immediately.

## Consequences

- Retry counts, backoff, and error classification are consistent across MAS, Deep Research, PaperOrchestra, and evaluation.
- A retry is a request retry, not a model or protocol selection mechanism.
- Capability-specific idempotency rules must be handled before enabling retries for side-effecting or non-repeatable operations.
