---
status: superseded by ADR-0082
---

# Serialize Concurrent Draft Appends

Concurrent observable events are written through one append lock. The capture operation assigns each Draft Block a monotonic sequence at the moment it appends, so blocks cannot interleave or overwrite one another; the original event timestamp, source, and correlation identifiers remain inside the block for reconstruction of causal timing. Capture does not wait for unrelated research tasks or reorder the file by model-reported timestamps.
