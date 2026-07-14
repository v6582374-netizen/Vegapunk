---
status: superseded by ADR-0094
---

# Use Candidate Artifacts, Not Report Links, for Evidence Carriers

The complete Candidate Experiment belonging to the Selected Research Candidate is the discovery-side source boundary for research-generated Evidence Carriers. Its recorded metrics, structured outputs, data products, existing images, method definition, code, and scientifically relevant run history remain available to the Manuscript Sculptor even when no `report/report.md` exists. A report-linked image is an optional reusable presentation asset, not the gate through which evidence becomes visible to the paper workflow.

Availability does not authorize indiscriminate inclusion. Discovery orchestration retains authority over run status and evidence validity; the Manuscript Sculptor may not treat the current valid run as an inferred best run, rehabilitate a failed or unmeasured result, or mix incompatible attempts. Earlier or failed-run material enters only when it has scientific value under ADR-0052, such as a valid negative result or ablation. Every included carrier remains traceable to the exact candidate artifacts and claims it represents; ADR-0057 governs generation when the required carrier does not yet exist.

Under ADR-0071, an Agent's exhausted final failure still reaches the Sculptor once. This makes scientifically meaningful negative evidence available for editorial judgment without making an intermediate retry, infrastructure error, or failed status sufficient evidence for a claim.

This supersedes ADR-0011. In particular, absence of `report/report.md`, absence of Markdown image links, or absence of files under `report/images/` no longer reduces the paper workflow's evidence source to an empty `figures/info.json` array. Literature evidence and citations remain governed by their existing Research Dossier contracts rather than by this experiment-artifact boundary.

**Considered Options**

- Keep `report/report.md` as the exclusive figure manifest. Rejected because ordinary auto tasks do not guarantee that artifact and the report is a lossy presentation rather than the scientific source of truth.
- Import every image from every Experiment Run. Rejected because discoverability is not evidence validity and would mix superseded, failed, or incompatible results.
- Use only the current valid run. Rejected because it would hide scientifically meaningful baselines, ablations, and negative results without establishing that the current run is globally best.
