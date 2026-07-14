---
status: accepted
---

# Preserve Existing Candidate Experiment Artifacts

PaperOrchestra will consume InternAgent's existing Discovery Launch, session, Candidate Experiment, and Experiment Run artifacts without changing how InternAgent creates, organizes, or serializes them. PaperOrchestra-side input preparation may read the existing `discovery_summary.json`, `traj.json`, `ideas.json`, run metrics, reports, images, and logs, but it may not require InternAgent to copy a complete Idea, configuration, lineage record, or new manifest into each Candidate Experiment.

This supersedes ADR-0003's plan to retrofit Candidate Experiment directories into a new self-contained artifact contract. PaperOrchestra keeps its own Run outputs at the Discovery Launch under ADR-0024's amended location contract.

**Considered Options**

- Reorganize Candidate Experiment production before porting PaperOrchestra. Rejected because the migration must treat existing InternAgent experiment production as fixed.
- Consume the existing artifacts where InternAgent already writes them. Accepted because the complete session trajectory and experiment artifacts can be joined on the PaperOrchestra side without changing the producer.
