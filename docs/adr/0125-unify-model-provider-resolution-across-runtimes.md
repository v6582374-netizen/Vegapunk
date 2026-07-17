# Unify Model Provider Resolution Across Runtimes

InternAgent and PaperOrchestra will use one project-wide Model Provider resolution and runtime path for every in-process LLM call, instead of maintaining a PaperOrchestra-specific factory or provider boundary.
This makes provider switching a single configuration decision and removes direct provider or model dispatch from individual runtimes, while keeping capability-specific differences explicit inside the unified runtime.

## Consequences

- PaperOrchestra becomes a consumer of the same runtime contract as the rest of InternAgent.
- Text, structured output, tools, vision, image generation, and embeddings remain explicit capabilities rather than being inferred from a provider name.
- Long Memory indices may be deleted and rebuilt when the selected Embedding Model changes; no cross-model index migration is required.
