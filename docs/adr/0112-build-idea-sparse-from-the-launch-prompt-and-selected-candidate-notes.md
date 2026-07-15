---
status: accepted
---

# Build idea_sparse from the Launch Prompt and Selected Candidate Notes

For the Initial Paper Baseline, when Terminal Candidate Selection succeeds, the Paper Idea Brief written to upstream `idea_sparse.md` is a deterministic Markdown projection of exactly two source artifacts: the Discovery Launch root `prompt.json` and the Selected Research Candidate root `notes.txt`. The former supplies the research problem, data, baseline, metrics, and constraints; the latter supplies the selected idea and method. The projection labels each source and does not call a model, summarize, infer, or alter their scientific content.

Candidate- and run-local copies of `prompt.json` are excluded because they duplicate the Launch-root file. `ideas.json`, Research Draft content, source code, code-derived material, and experimental outcomes are also excluded: they either mix competing candidates, violate the Initial Paper Baseline, or belong in the Experimental Record rather than the method-focused Paper Idea Brief. This decision narrows the deterministic projection required by ADR-0110 and applies only when the Selected Research Candidate required by ADR-0111 exists; selection-free fallback material remains a separate decision.
