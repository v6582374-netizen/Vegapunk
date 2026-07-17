Status: superseded by ADR-0148

# Load the Catalog on Runtime Construction

The Unified Model Runtime will read `model_catalog.yaml` once when a process constructs it and will not implement hot reload or a cross-process configuration lock.
When a process is interrupted and later restarted, the new Runtime reads the current Catalog so an explicit configuration change can apply to the unfinished work; no persisted model snapshot blocks that normal restart behavior.

## Consequences

- A running process naturally keeps one in-memory configuration without requiring an additional freeze mechanism.
- Resume behavior follows the current configuration at restart time.
- Telemetry records the actual canonical model identities used, but configuration history is not treated as a resume constraint.
