Status: accepted

# Make Skill Management Anonymous and Local-First

Skill Management will not own an account, sign-in flow, profile, token store, cloud identity, or account-gated feature.
Editing, tool synchronization, risk scanning, translation, favorites, tags, import/export, usage monitoring, and anonymous feedback remain available through local state or explicitly configured local services without bridging to the Desktop App's separate cloud identity.
Remote Marketplace browsing, installation, updates, and community interactions are excluded by ADR-0165.
Cross-device Skill synchronization, if needed later, must be designed as a Desktop App capability rather than restoring the removed Skill Management account system.

Cloud Skill Synchronization is not part of Version 1.
Local Tool Synchronization remains part of Skill Management, and local import/export is the portable transfer mechanism.

Skill Management retains its Local Skill Usage Monitor but does not own Desktop Product Telemetry.

## Consequences

- GitHub and Google OAuth, auth-session persistence, refresh tokens, logout, avatar UI, and auth deep links are removed from Skill Management.
- Local metadata remains first-class capability; remote Marketplace access is not part of Skill Management.
- Cloud sync preferences, vault backup consent, and cloud sync state are removed rather than left as inert account-dependent settings.
- Skill invocation counts remain local, while product-usage telemetry is either absent or controlled only by a future Desktop App privacy surface.
- The Desktop App's existing cloud account remains outside the Skill Management boundary until a separate identity decision is made.
- Upgrade migration clears old Skill Manager auth tokens and remote state while preserving local Skills, tags, favorites, tools, projects, and local synchronization preferences.
