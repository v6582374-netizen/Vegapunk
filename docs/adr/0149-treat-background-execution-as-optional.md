Status: superseded by ADR-0154

# Treat Background Execution as Optional

Background Model Execution is an optional Provider capability rather than a required text-generation semantic.
The relay may preserve its current background Responses behavior, while Qwen uses synchronous Responses with the same request and result contract; Runtime timeout, centralized concurrency, and bounded retries protect long Qwen calls.

## Consequences

- Qwen does not need to emulate server-side background jobs or response polling.
- Qwen runs do not provide the relay's server-side response checkpoint recovery, which is accepted as an execution difference.
- Capability Preflight must not reject a model solely because it lacks Background Model Execution when the owning role can run synchronously.

## Verification

On 2026-07-17, a minimal request to the configured DashScope Responses endpoint using `qwen3.7-max` returned HTTP 200 and `status=completed` with `background=false`.
The same request with `background=true` returned HTTP 400 with `Currently not support background.`
The successful response contained both a `reasoning` output item and an assistant message with `output_text`, confirming the synchronous Responses shape needed by the shared adapter.
