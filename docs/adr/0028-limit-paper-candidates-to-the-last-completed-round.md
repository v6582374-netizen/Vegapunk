---
status: superseded by ADR-0031
---

# Limit Paper Candidates to the Last Completed Round

The paper-candidate pool contains only the Candidate Experiments from the last completed Discovery Round. PaperOrchestra will not compare candidates across every historical round, because in the default incremental workflow each earlier round has already selected the baseline carried into the next round; the only missing convergence is after the final round, where Vegapunk records all results but does not call its between-round best-result helper.

This decision defines only the candidate pool. The rule for selecting one Candidate Experiment from that final round, including missing metrics and ties, remains a separate decision and must not be inferred.

**Considered Options**

- Compare Candidate Experiments from every Discovery Round again. Rejected because it duplicates the incremental relay decisions and expands the migration beyond the missing final convergence.
- Use Vegapunk's recorded `final_best_code_path` directly. Rejected because that path is selected before the last round and does not identify one of the final round's newly executed Candidate Experiments.
