# Declare Model Capabilities in the Catalog

Each Canonical Model Identity will carry an explicit Capability Declaration in the Unified Model Catalog.
Capability Preflight will use this declaration as its authoritative input; Provider model listings and runtime probes may verify the declaration but will not silently change routing decisions.

## Consequences

- Capability declarations are versioned project configuration rather than undocumented adapter assumptions.
- A model can expose text, structured output, tools, vision, image generation, or embeddings independently.
- Incorrect declarations are caught by targeted probes and tests, while production routing remains deterministic.
