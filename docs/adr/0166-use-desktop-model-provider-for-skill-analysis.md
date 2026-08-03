Status: superseded by ADR-0172

# Use the Desktop Model Provider for Skill Analysis

ADR 0172 removes Skill translation, risk scanning, and other AI analysis from the current Skill Management scope.
This ADR is retained as historical context for the previously considered shared-provider design.
Those operations consume the Desktop App's shared Models/Providers settings, so base URLs, model identities, and credentials have one owner.

## Consequences

- Local Skill analysis remains available without a Skill Management account.
- The Skill Manager LLM settings card and duplicate API-key storage are removed.
- A provider outage or missing provider is reported as an analysis capability state, not as an account or Marketplace failure.
