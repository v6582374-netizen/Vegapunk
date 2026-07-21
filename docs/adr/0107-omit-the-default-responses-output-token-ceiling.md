---
status: accepted
---

# Omit the Default Responses Output Token Ceiling

Vegapunk will keep `max_output_tokens` as an optional per-request control, but the default Responses request will omit the field entirely. A missing configuration value must not be serialized as JSON `null`; the adapter must distinguish “unset” from an explicit numeric ceiling. This follows the Responses API's optional parameter semantics and avoids relying on the one-account relay to interpret `null`, while preserving bounded short calls that explicitly request a ceiling.

The two legacy short caps in `ExpAnalyzeAgent` (`10` and `50`) are removed rather than replaced with arbitrary numbers. They were inherited from the former Chat Completions path; the first is below the Responses minimum and the second can still truncate reasoning-heavy work.

**Considered Options**

- Keep the global default at `128000`. Rejected because the value was introduced as a quality-first migration default, is not required by the protocol, and may exceed a compatible relay's accepted range.
- Serialize `null` to disable the ceiling. Rejected because `null` is a distinct wire value from an omitted optional field and the relay's handling is not guaranteed.
- Remove the field from the Runtime contract entirely. Rejected because callers such as metric analysis and tool loops need explicit small ceilings for bounded responses.
