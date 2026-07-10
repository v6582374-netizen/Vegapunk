---
status: superseded by ADR-0021
---

# Candidate Experiment as Reproducibility Boundary

Each Candidate Experiment will own a self-contained artifact directory that records its immutable idea and task inputs, baseline lineage, configuration, all Experiment Runs, logs, metrics, outputs, reports, and a manifest connecting them. Each Experiment Run remains independently reproducible inside that directory. Discovery Launch and session directories retain aggregate indexes rather than owning candidate evidence, while cross-experiment memory remains an external cache referenced by identity and version. Incremental discovery inherits an explicit baseline export instead of copying an earlier Candidate Experiment wholesale.

**Considered Options**

- Treat each Experiment Run as the top-level reproducibility boundary. Rejected because it duplicates the idea, lineage, and comparison context shared by all attempts.
- Treat the entire Discovery Launch as the only reproducibility boundary. Rejected because it entangles unrelated candidates and makes individual experiments difficult to inspect, replay, or reuse.
