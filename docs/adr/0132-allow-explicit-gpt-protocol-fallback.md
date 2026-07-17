Status: superseded by ADR-0133

# Allow Explicit GPT Protocol Fallback

Relay GPT model entries may explicitly declare `responses` as their preferred protocol and `chat_completions` as a fallback protocol.
The fallback is attempted only after a known Responses protocol-compatibility error, keeps the same Provider and model identity, and is never inferred from a model-name prefix or applied to other Providers.

## Consequences

- The runtime must distinguish protocol incompatibility from authentication, quota, timeout, server, content, and model errors.
- Every fallback must be observable and record the protocol actually used.
- A fallback is valid only when the requested Runtime capabilities are supported by the fallback protocol; unsupported requests still fail explicitly.
