---
status: accepted
---

# Build the Experimental Record from Narrative and Exact Run Artifacts

For the Initial Paper Baseline, when Terminal Candidate Selection succeeds, upstream `experimental_log.md` is a deterministic rendering of the Selected Research Candidate's experiment narrative, baseline, and every numbered Experiment Run. The narrative is the Candidate-root `experiment_report.txt` when it exists, otherwise the Candidate-root `log.txt`. The renderer then presents `run_0` followed by every `run_N` in numeric order, embedding each existing `final_info.json`, `report/report.md`, and `traceback.log` without model preprocessing or scientific-content rewriting.

`final_info.json` is authoritative when narrative text conflicts with recorded measurements. Candidate-root `experiment_report.txt` is only a narrative index; it cannot replace or override exact Run artifacts. Candidate-root `log.txt` is a fallback rather than duplicate input, and copied `run_N/log.txt` snapshots are excluded. Complete `discovery_summary.json`, Candidate Selection Provenance, source code, code summaries, and code differences remain outside the upstream model context; summary and selection records may still be used by the adapter to locate the candidate and preserve an audit trail.

This supersedes ADR-0010. In particular, the earlier contract omitted `experiment_report.txt`, exposed only the path to a failure traceback, and did not define the Candidate-root log fallback or numerical source precedence.
