# Bind Text and Image Models to One Provider

The text model and image-generation model will remain separate canonical model identities because they serve different capabilities, but both bindings must belong to the same Model Provider within a run.
When the active text identity changes from `relay/...` to `qwen/...`, the configured image identity must also be a `qwen/...` model; the runtime will not silently use a relay image model as a fallback.

## Consequences

- A Provider Catalog must describe multiple capability-specific models under one Provider.
- Capability Preflight must validate both model identities and their shared Provider.
- A Provider without a configured image model cannot run Paper plotting with `use_plotting: true`.
