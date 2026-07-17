# Limit the Active Provider Set to Relay and Qwen

The project runtime will resolve only the `relay` and `qwen` Model Providers for in-process text and image calls.
The former `openai`, OpenRouter, InternS1, DSR1, DeepSeek, and Gemini provider identities are removed from the Catalog and active dispatch; inactive vendored implementations do not count as supported project Providers.

## Consequences

- Selecting a removed Provider fails during configuration validation.
- The runtime and tests no longer need to preserve historical Provider-specific routing branches.
- Third-party CAMEL provider implementations may remain physically present when they are not part of the active project surface.
