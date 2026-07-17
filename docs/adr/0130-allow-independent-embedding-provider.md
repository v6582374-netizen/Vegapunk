# Allow an Independent Embedding Provider

Embedding Model selection will remain inside the Unified Model Catalog but may use a different Model Provider from the Active Text Model and image model.
Embedding is retrieval infrastructure rather than scientific content generation, so a local, Qwen, or relay embedding service may be selected independently; changing it permits deleting and rebuilding the disposable Long Memory Index instead of migrating vectors.

## Consequences

- Text and image bindings still share one Provider, while the embedding binding does not.
- Capability Preflight must validate the embedding binding separately when Long Memory is enabled.
- Model switching documentation must distinguish content-generation changes from retrieval-index changes.
