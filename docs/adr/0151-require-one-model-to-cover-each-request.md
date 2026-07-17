Status: superseded by ADR-0152

# Require One Model to Cover Each Request

Each Runtime request will resolve to exactly one Canonical Model Identity that covers every capability required by that request.
The runtime will not silently split one request across a primary and auxiliary model; multi-model orchestration, if needed later, is a separate explicit workflow capability.

## Consequences

- Vision requests use the vision binding only when that model also supports the request's reasoning, structured-output, and tool requirements.
- Capability Preflight and request validation must operate on capability sets rather than on Agent names or model-name strings.
- Auxiliary bindings reduce configuration scattering without creating hidden multi-model pipelines.
