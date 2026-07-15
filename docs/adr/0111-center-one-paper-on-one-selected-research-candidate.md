---
status: accepted
---

# Center One Paper on One Selected Research Candidate

When Terminal Candidate Selection succeeds, candidate-local content in the Paper Input Bundle comes only from that one Selected Research Candidate. Every Experiment Run belonging to the selected candidate remains in scope through its recorded outcomes, reports, logs, and non-code outputs, including failed attempts and earlier iterations, while sibling candidates are excluded even when they succeeded in the same Paper Candidate Round. Source code remains outside the initial bundle under ADR-0110. Launch-level task context and citations remain shared model inputs; `discovery_summary.json` and Candidate Selection Provenance remain available to the adapter for candidate location and audit but stay outside the upstream model context under ADR-0113.

This matches PaperOrchestra's singular `idea_sparse.md` and `experimental_log.md` contract: one paper describes one coherent method while retaining the complete experimental trajectory used to develop and evaluate it. Supplying other candidates would introduce competing methods that the upstream pipeline has no explicit comparison or separation contract for. ADR-0110 remains authoritative when no Selected Research Candidate exists; this decision does not make selection a prerequisite for Paper Handoff.

**Considered Options**

- Include every successful candidate from the Paper Candidate Round as comparison material. Rejected because the writing pipeline could blend independent methods into one paper instead of treating them as controlled baselines.
- Include only the selected candidate's final successful Experiment Run. Rejected because earlier runs, failures, and corrections can provide valid ablations, limitations, and evidence for the final method.
