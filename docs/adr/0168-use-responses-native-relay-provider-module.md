---
status: accepted
---

# Use a Responses-Native Relay Provider Module

The Models settings surface will expose Relay as a complete provider module backed by a Responses-native adapter.
The module will use the existing project-wide `relay` Provider identity and its declared Responses protocol.
Relay will not be registered as a generic Chat Completions compatibility provider merely to reuse the existing desktop provider path.
The module will not silently fall back to Chat Completions when a Responses request fails.
The connection will default to the project's current Relay deployment and expose Endpoint editing only as an explicitly supported advanced setting.
Relay will use the shared provider gallery and detail form, with the Endpoint override rendered through the same advanced-setting disclosure as other keyed providers.
The first Relay module will recommend `gpt-5.6-sol` for text generation, will exclude image models from this configuration surface, and will accept an explicitly entered Relay model identity.

## Consequences

- The Relay card, configuration form, verification action, model suggestions, and actual model calls share one explicit provider identity.
- The initial model surface stays text-only while permitting a user-supplied Relay model ID instead of pretending that the curated recommendation is exhaustive.
- The Relay entry uses the shared provider gallery and provider detail form, so selecting it follows the same card-to-detail flow as every other provider.
- Reasoning, tool use, structured output, and continuation behavior remain part of the Relay module contract instead of being reduced to the lowest common denominator.
- The desktop provider layer needs a Responses request and streaming boundary in addition to its current Chat Completions path.
- Protocol incompatibility is an explicit failure and requires a separate architectural decision before any fallback is introduced.

**Considered Options**

- Add Relay through the existing generic OpenAI-compatible descriptor.
  Rejected because that path calls Chat Completions and would not preserve the declared Relay semantics.
- Add Relay through Chat Completions first and switch protocols after the card works.
  Rejected because the first usable contract would already encode the wrong capability boundary.
- Add a silent Responses-to-Chat fallback.
  Rejected because a successful fallback could discard reasoning state, tool-call structure, or continuation semantics without making the downgrade visible.
