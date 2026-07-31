Status: accepted

# Use the Desktop Model Provider for Skill Analysis

Local Skill translation and optional deep risk review may call a configured model service, but Skill Management will not own a separate LLM provider configuration.
Those operations consume the Desktop App's shared Models/Providers settings, so base URLs, model identities, and credentials have one owner.

## Consequences

- Local Skill analysis remains available without a Skill Management account.
- The Skill Manager LLM settings card and duplicate API-key storage are removed.
- A provider outage or missing provider is reported as an analysis capability state, not as an account or Marketplace failure.
