# Use One Model Catalog File

All in-process model identities, Provider Configuration, protocol declarations, capability declarations, and the three root model bindings will live in `config/model_catalog.yaml`.
Workflow configuration files may control stages, feature flags, concurrency, and memory behavior, but they will not contain model names, Provider settings, credentials, or endpoints.

## Consequences

- Vegapunk, Deep Research, PaperOrchestra, and evaluation read one source of model truth.
- Provider switching does not require synchronized edits across workflow-specific YAML files.
- The Catalog file becomes the schema boundary for model configuration and Capability Preflight.
