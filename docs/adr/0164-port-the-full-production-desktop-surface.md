Status: accepted

# Port the Full Production Desktop Surface

The Linux Web Counterpart will cover every production user-visible surface and flow reachable through normal navigation in the macOS Desktop Baseline, including the main workspace, Discovery, settings, integrations, Inbox, automations, and Skills Manager. Test harnesses, internal prototype variants, and the native Tauri shell are not standalone parity targets; their user-visible capabilities are migrated through browser-compatible adapters or recorded Platform Capability Exceptions.

## Considered Options

- Port only Vegapunk-specific Discovery screens: rejected because it would not satisfy full parity and would leave the baseline's primary workspace incomplete.
- Port only the current `main/frontend`: rejected because it is not the macOS baseline.

## Consequences

- The work must be tracked as a surface inventory rather than a single page rewrite.
- PRs may be split by capability, but release acceptance requires every production route and flow to be represented in the inventory.
- Tauri-only shell behavior is evaluated separately as a capability migration, not silently omitted.
