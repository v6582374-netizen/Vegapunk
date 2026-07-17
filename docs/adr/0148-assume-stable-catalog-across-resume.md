Status: accepted

# Assume a Stable Catalog Across Resume

The runtime will not support changing the Model Catalog while a process is running, and recovery after interruption assumes that the same Catalog and model bindings remain in effect.
Provider-specific response state may continue to use its existing mechanism; catalog changes between interruption and resume are outside the supported workflow and require no migration, replay, or compatibility logic.

## Consequences

- No hot reload or cross-Provider response-state migration is added to the Unified Model Runtime.
- A resumed workflow must use the same Provider, model identities, protocols, and capability declarations as the interrupted process.
- Users who intentionally change models start a new run rather than resuming the old one.
