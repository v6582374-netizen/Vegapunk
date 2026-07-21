---
status: accepted
---

# Separate DR Model Selection from Provider Deployment

Deep Research keeps its existing independent model selection for its default, planning, execution, synthesis, and extraction roles, while reusing the provider endpoint, credentials, Responses transport, caching, and response-state policy resolved by Vegapunk. DR role overrides recursively merge over the selected DR workflow configuration; unspecified roles inherit the DR default model. DRAgent must not hard-code a model, extraction-specific environment variables must not silently change routing, and an enabled DR workflow must validate model availability once before starting parallel work so authorization failures stop early instead of producing retry storms.

This preserves the useful autonomy of the embedded DR workflow without maintaining a second provider deployment or introducing a new project-wide configuration system.
