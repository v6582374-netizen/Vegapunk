# Centralize Provider Configuration

All Provider Configuration will be owned by the project-wide Unified Model Catalog.
Agents, PaperOrchestra, evaluators, and other in-process callers may select a Canonical Model Identity but may not override credentials, endpoints, headers, protocol, or Provider-specific runtime settings at the call site.

## Consequences

- `relay` and `qwen` credentials are configured once and resolved from their Provider entries.
- A provider switch changes a model identity rather than requiring edits across runtime consumers.
- Provider-specific behavior is tested at the Catalog and adapter boundary instead of being duplicated in callers.
