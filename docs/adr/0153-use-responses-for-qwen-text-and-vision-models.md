Status: accepted

# Use Responses for Qwen Text and Vision Models

Qwen text and vision model entries that support Alibaba Cloud's OpenAI-compatible Responses API will declare `protocol: responses` and share the Unified Model Runtime's Responses adapter with `relay`.
Chat Completions remains available only for a model explicitly documented and tested as Chat-only; no runtime protocol fallback is introduced.

## Consequences

- Qwen-specific request omissions, such as unsupported background execution, are represented in the fixed Provider/model policy rather than by choosing a different adapter at runtime.
- Responses response-shape differences are normalized inside the shared adapter boundary.
- Adding a Chat-only Qwen model requires a separate explicit Catalog entry and contract probe.
