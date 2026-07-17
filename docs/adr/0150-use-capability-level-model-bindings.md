Status: accepted

# Use Capability-Level Model Bindings

The Catalog will keep one `active_text_model` for pure text operations and a `capability_models` map for fixed capability operations such as vision, image generation, and embeddings.
Agent names and workflow roles will not select models directly; each operation entry point is wired to its configured binding before a run begins.

## Consequences

- Adding a new capability does not create another set of Agent-specific model overrides.
- Text and image-generation models remain separate bindings under the same Provider when required.
- Embedding remains independently selectable because it is retrieval infrastructure.
