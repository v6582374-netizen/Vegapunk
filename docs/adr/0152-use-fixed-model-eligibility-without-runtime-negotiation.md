Status: accepted

# Use Fixed Model Eligibility Without Runtime Negotiation

Model bindings and their capability eligibility will be designed and verified during development, then selected statically in the Unified Model Catalog.
The Unified Model Runtime will dispatch fixed operations to fixed bindings and will not infer request capabilities, negotiate models per request, or split one request across multiple models.

## Consequences

- Unsupported models are excluded before they enter the supported Catalog through documentation review, targeted probes, and E2E tests.
- Runtime validation is limited to configuration shape, referenced model identities, and fixed binding completeness.
- Adding a model requires a development-time eligibility check and Catalog update, not a new dynamic routing algorithm.
