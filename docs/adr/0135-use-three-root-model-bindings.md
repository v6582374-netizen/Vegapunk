# Use Three Root Model Bindings

The project configuration will expose exactly three in-process model bindings: `active_text_model`, `image_model`, and `embedding_model`.
All text-producing and text-evaluating roles follow `active_text_model`; PaperOrchestra plotting uses `image_model` when enabled; Long Memory uses `embedding_model` independently.

## Consequences

- Writer, reflection, plotting-text, scorer, and Deep Research text model overrides are removed.
- Image and embedding selection remain explicit capability roles rather than hidden provider fallbacks.
- The Experiment Backend model remains outside this contract because it is independently selected.
