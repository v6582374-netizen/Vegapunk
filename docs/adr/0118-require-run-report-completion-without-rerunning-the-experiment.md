---
status: superseded by ADR-0122
---

# Require Run Report Completion Without Rerunning the Experiment

An executed Experiment Run is complete and eligible to count as successful only when it has both its valid outcome artifacts, including `final_info.json`, and its required Run Report at `report/report.md`. If the outcome artifacts already exist but the Run Report is missing, InternAgent keeps the same `run_N` and asks the same experiment backend to repair only the report from the Run's existing artifacts.

Report repair must not invoke the experiment launcher, modify code, alter metrics or other recorded results, create a new Experiment Run, or generate new experimental figures. It may only write the missing report and reference existing images already produced by that Run. Candidate-root `experiment_report.txt` is not a substitute, and PaperOrchestra never performs this repair after Paper Handoff.

If report repair does not produce a valid Run Report, the recorded results remain available for audit and the Experimental Record, but the Run remains incomplete and cannot satisfy successful-run or candidate-selection requirements. This extends ADR-0117 without treating a missing presentation artifact as permission to repeat an expensive experiment.
