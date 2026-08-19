# OpenWorker upstream provenance

- Upstream repository: `https://github.com/andrewyng/openworker.git`
- Upstream ref: `main`
- Imported source commit: `3766805d10586c19f83cc9132de8c7e1894c24c7`
- Subtree prefix: `desktop/openworker/upstream/`
- Import purpose: source baseline for the OpenWorker-native Prompt Library settings module (GitHub issue #35).
- Local adaptation policy: local changes are recorded in explicit `adapt(openworker): ...` commits. Future upstream releases are reviewed as diffs and selectively adapted; they are not automatically merged into the customized source tree.
- Linux Web Counterpart: the server-hosted build reuses `surfaces/gui` verbatim for pixel parity; Web hosting/authentication changes live at the server boundary and are not a second frontend.

## Local adaptation registry

### Removal of OpenWorker Cloud

The entire OpenWorker Cloud capability is removed from this tree. The criterion
was whether a feature can work without the upstream broker: anything that cannot
was deleted outright rather than kept behind a flag or degraded path.

Removed: Auth0 PKCE sign-in, the managed OAuth broker, telemetry, the persona
gallery, GitHub App installation-token minting, the desktop-to-cloud relay
WebSocket (with its Slack/GitHub inbound adapters), and the connectors' managed
layer (one-click OAuth, `mode="relay"`, multi-workspace and multi-installation
routing).

Retained: manual token paste for every connector, Slack Socket Mode, GitHub PAT,
MCP local OAuth (no cloud account required), and the generic multi-account
storage layer (`accounts.py`, `gmail_accounts`, `gcal_accounts`,
`hubspot_portals`), whose profile fields are field-compatible with manual paste.

Consequences worth knowing when reviewing an upstream diff:

- Slack is single-workspace. Per-team profiles (`slack:team:*`), `TeamAuth`, and
  team-qualified addressing (`T…/C…`) are gone; allow-lists are flat again.
- GitHub is `two_way=False` and is not a gateway listener platform — inbound
  mentions arrived only over the relay.
- Sender attribution is deleted: it named the managed OAuth installer, which
  Socket Mode never has.
- `Config` no longer carries `cloud_*` fields, and `/auth/callback` plus
  `/oauth/callback` are gone (removed from the tokenless-path allowlist too).
- Orphaned SecretStore entries (`cloud:auth`, `cloud:telemetry`, `slack:team:*`,
  `github:install:*`) are left unread rather than migrated.
