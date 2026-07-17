Status: accepted

# Disable Background Model Execution Globally

The unified runtime will send all text, vision, image, and embedding requests with background execution disabled.
This removes Provider-specific asynchronous submission, polling, and background checkpoint branches so relay and Qwen share one execution semantic; long requests are handled by the shared timeout, concurrency, and bounded retry policies.

## Consequences

- Provider Configuration no longer exposes a background execution switch.
- Background-specific response checkpoint state is removed from the active runtime contract.
- Ordinary Responses context continuation, such as `previous_response_id` where supported, remains independent from background execution.
