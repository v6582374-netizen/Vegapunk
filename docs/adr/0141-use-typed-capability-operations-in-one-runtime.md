Status: accepted

# Use Typed Capability Operations in One Runtime

The Unified Model Runtime will expose one primary typed text-inference operation and separate typed operations for image generation and embeddings.
Text, JSON, tool, and vision requests share the text-inference contract; image and embedding operations remain capability-specific because their payloads, results, and validation rules are fundamentally different.

## Consequences

- Convenience methods such as `generate` and `generate_json` are thin wrappers over the text operation.
- No consumer receives Provider-specific methods or SDK response objects as its primary contract.
- Capability-specific operations still share Catalog resolution, client lifecycle, telemetry, and error classification.
