# Use Explicit Provider/Model Identities

Every selectable model will be represented by one explicit `provider/model` identity, such as `relay/gpt-5.6-sol` or `qwen/qwen3-max`, and the active text role will select one such identity.
The current OpenAI-compatible relay is named `relay` rather than `openai` so that the configured Provider identity matches the service boundary and changing the active identity remains a single-field configuration change.

## Consequences

- Provider credentials, endpoints, and capabilities remain in the Catalog while role configuration stores only canonical identities.
- Model names are never translated through compatibility aliases or used to infer a different Provider.
- Existing `default_provider` plus caller-local `model_name` configurations must be removed or converted to canonical identities.
