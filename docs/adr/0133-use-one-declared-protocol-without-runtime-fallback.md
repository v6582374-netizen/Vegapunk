# Use One Declared Protocol Without Runtime Fallback

The unified runtime will use exactly one protocol declared by each Canonical Model Identity and will not retry a failed request through another protocol.
The previously considered GPT Responses-to-Chat fallback is rejected because it increases routing complexity and can change request semantics; protocol incompatibility fails explicitly instead.

## Consequences

- Capability Preflight validates the single declared protocol for each enabled role.
- Responses, Chat Completions, Image, and Embeddings remain separate explicit protocol choices.
- A future protocol fallback would require a new architectural decision rather than a local adapter change.
