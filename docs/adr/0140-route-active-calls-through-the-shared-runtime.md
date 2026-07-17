Status: accepted

# Route Active Calls Through the Shared Runtime

All active in-process callers, including vendored PaperOrchestra helpers, will use one injected Unified Model Runtime.
Consumers will not create Provider SDK clients, resolve model identities, or select protocols locally; the shared runtime owns Catalog resolution, Capability Preflight, adapter selection, telemetry, and error classification.

## Consequences

- PaperOrchestra's synchronous helpers need a bridge to the shared runtime rather than a second factory or client.
- Deep Research and evaluation use the same runtime instance or runtime contract as the main MAS agents.
- Tests can exercise Provider behavior at one boundary and use injected runtime doubles for consumer tests.
