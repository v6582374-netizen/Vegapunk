---
status: superseded by ADR-0122
---

# Produce Run Reports by Default and Use Them as Figure Manifests

Every newly executed InternAgent Experiment Run produces a Run Report at `report/report.md` by default, across task types and experiment backends. The report is part of normal Discovery execution, not a PaperOrchestra preprocessing step or the separate report-only launch mode. It records that Run's results and explicitly references every publication-eligible image already produced by the Experiment; PaperOrchestra never generates or backfills a missing Run Report.

For the Initial Paper Baseline, an existing Experiment image is eligible for the Paper Input Bundle only when the corresponding Run Report contains an explicit Markdown image reference to it. The reference must resolve to an existing file within the same Experiment Run boundary. Eligible files are copied without pixel modification and retain their Run-relative provenance; unreferenced files under `outputs/`, `report/`, or other directories remain excluded as possible diagnostics, caches, or intermediate artifacts.

The existing `--mode report` option remains a separate workflow that skips experiment execution and is not made the default. The current sci-task Claude prompt already requires a Run Report, but the generic auto-task prompt and other backend paths must be brought under the same default artifact contract. ADR-0118 resolves missing-report handling: the Run is incomplete until the same experiment backend repairs the report without rerunning the experiment.
