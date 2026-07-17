Status: accepted

# Use One Explicit Runtime Instance per Process

Each process will construct one Unified Model Runtime and inject it into all active in-process consumers.
The Runtime may cache Provider clients and request metadata by canonical model identity, but it will not be a hidden module-level singleton; tests and isolated workflows can construct independent instances.

## Consequences

- MAS, Deep Research, PaperOrchestra, and evaluation share one client lifecycle and telemetry boundary.
- Runtime state is scoped to a process and cannot leak through global module state between tests or runs.
- Synchronous consumers use a bridge over the same injected instance rather than constructing another Runtime.
