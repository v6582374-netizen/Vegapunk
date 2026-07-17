Status: accepted

# Centralize Provider Request Concurrency

The Unified Model Runtime will own admission control for requests sent to each Provider, using Provider-specific concurrency limits from the Unified Model Catalog.
Workflow-level worker counts may control task scheduling, but PaperOrchestra, Deep Research, and other consumers will not maintain independent model-request semaphores.

## Consequences

- Provider rate and account limits are enforced at one boundary across all consumers.
- Workflow parallelism and Provider request concurrency become separate concepts.
- Tests can verify request admission without running the full workflow orchestration.
