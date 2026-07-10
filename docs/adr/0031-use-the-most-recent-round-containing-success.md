---
status: accepted
---

# Use the Most Recent Round Containing Success

Starting with the last completed Discovery Round, PaperOrchestra scans completed rounds backward and selects the first round containing at least one Candidate Experiment whose recorded result has `success: true`. This Paper Candidate Round is the complete candidate pool: older rounds are not compared after it is found, and no candidates from different rounds are ranked against one another.

If the Paper Candidate Round contains exactly one successful Candidate Experiment, that candidate is selected directly without metric comparison. If it contains multiple successful candidates, the separate explicit-metric selection rule applies. If no completed round contains a successful candidate, Dossier writing stops before model invocation because the Discovery Launch has no eligible scientific subject.

This supersedes ADR-0028's final-round-only candidate pool and ADR-0030's final-round-specific cardinality rule.

**Considered Options**

- Stop immediately when the final round has no successful candidates. Rejected because an earlier round may contain the latest usable successful experiment.
- Compare successful candidates across all rounds. Rejected because fallback should find the nearest usable round, not reopen every incremental relay decision.
