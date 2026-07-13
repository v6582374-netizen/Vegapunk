---
status: accepted
---

# Keep the Research Narrative Publication-Oriented

The Research Dossier remains the canonical output of a Discovery Launch because a prose paper cannot replace authoritative evidence, but its Research Narrative is a publication-oriented scientific manuscript rather than a self-explaining reproduction manual. The Living Manuscript therefore has no mandatory `复现指南` section. Details needed to understand, assess, or repeat the scientific result remain in the appropriate Method, Experimental Setup, Evaluation, or other argument-bearing sections; these include the material data conditions, evaluation protocol, metrics, experimental settings, randomization, statistical treatment, and compute conditions demanded by the actual claims.

Step-by-step environment setup, execution commands, dependency locks, complete configuration dumps, artifact maps, integrity checks, troubleshooting, and end-to-end verification procedures move outside the main body to an appendix, supplementary material, project README, or another companion artifact in the Research Dossier. Moving those operational instructions does not permit the Manuscript Sculptor to omit scientifically necessary reproducibility details, and the companion material remains traceable to the authoritative experiment artifacts.

This supersedes ADR-0004 while preserving its decisions that the Research Dossier is the canonical launch output and that code, configurations, logs, and measured outputs remain authoritative. It also supersedes ADR-0008's mandatory `复现指南` clause and complements ADR-0052's exclusion of scientifically irrelevant process history.

**Considered Options**

- Keep a mandatory main-body `复现指南`. Rejected because step-by-step operational instructions consume publication space and interrupt the scientific argument.
- Remove reproduction information from the paper entirely. Rejected because reviewers still need enough methodological and experimental detail to assess and repeat the claimed result.
- Make the manuscript the only reproducibility artifact. Rejected because prose is a lossy and fragile representation of executable environments, configurations, and outputs.
