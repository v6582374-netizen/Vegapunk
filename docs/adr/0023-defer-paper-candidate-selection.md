---
status: superseded by ADR-0037
---

# Defer Paper Candidate Selection

A Discovery Launch still produces at most one Research Dossier, but no paper-candidate selection mechanism is currently accepted. Explicit selection, metric-based automatic selection, tie handling, and an `Awaiting Candidate Selection` state must not be implemented until the candidate-selection problem is examined as its own design topic.

This supersedes ADR-0001's selection rules while preserving its single-dossier boundary. The post-discovery trigger may start the Dossier Service, but it must not treat Vegapunk's incremental baseline choice, latest directory, first successful result, or any newly inferred metric as the Selected Research Candidate.
