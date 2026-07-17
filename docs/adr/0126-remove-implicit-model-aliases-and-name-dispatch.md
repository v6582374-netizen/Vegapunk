# Remove Implicit Model Aliases and Name-Based Provider Dispatch

The unified runtime will send canonical Provider and model identifiers directly to the selected adapter.
Legacy compatibility aliases such as Gemini names translated to GPT models, Deep Research model-name prefix dispatch, and PaperOrchestra protocol branching based on `gpt` or `gemini` substrings will be removed so that configuration, telemetry, and the actual request identify the same model and capability path.

## Consequences

- Vendored PaperOrchestra defaults, CLI values, and tests must use canonical model identities rather than upstream Gemini names.
- Provider and protocol selection comes from the Unified Model Catalog and capability metadata, not from model-name string inspection.
- Unsupported model capabilities fail explicitly instead of silently changing the requested model or protocol.
