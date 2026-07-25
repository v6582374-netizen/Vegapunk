Status: superseded by ADR-0162

# Render Research Identity with Seeded 2D Canvas Fields

Version 1 will render non-data-bearing Research Identity Layer graphics as deterministic 2D Canvas point-cloud fields derived from a stable project or module identity.
The approach preserves a distinctive computational-research identity without external image generation, per-project asset maintenance, or a WebGL rendering subsystem.

## Consequences

- Every field has a static CSS or text fallback and respects reduced-motion preferences.
- Canvas animation is brief and event-driven rather than a perpetual background effect.
- The graphics never represent runtime telemetry, research evidence, model topology, or other real data without an explicitly labelled data-visualization feature.
