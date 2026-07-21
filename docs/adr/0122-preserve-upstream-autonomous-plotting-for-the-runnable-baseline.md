---
status: accepted
---

# Preserve Upstream Autonomous Plotting for the Runnable Baseline

The first runnable PaperOrchestra baseline preserves the fixed upstream plotting workflow: PaperOrchestra may autonomously decide which plots or diagrams to create and may generate, caption, critique, and revise them through its existing Plotting Agent. The Vegapunk adapter will not add figure-provenance gates, existing-image catalogs, deduplication, restricted plot types, mandatory caption inputs, or a hybrid generated/existing figure path before the end-to-end pipeline has been demonstrated.

An existing `report/report.md` remains eligible input to `experimental_log.md`, but its absence does not make an Experiment Run incomplete, prevent candidate selection, or block Paper Handoff. This prioritizes a source-faithful runnable control baseline over speculative figure-policy safeguards and supersedes ADR-0114 and ADR-0116 through ADR-0121; ADR-0115 remains superseded.
