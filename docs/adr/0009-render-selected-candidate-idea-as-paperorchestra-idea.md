---
status: accepted
---

# Render the Selected Candidate Idea as PaperOrchestra idea.md

PaperOrchestra's `idea.md` will be a deterministic Markdown rendering of the complete InternAgent Idea record belonging to the Selected Research Candidate. The renderer may arrange explicit fields under stable headings but may not call a model, summarize, supplement, or infer missing content. The method presented to PaperOrchestra must follow the same precedence as InternAgent's experiment executor: non-empty `refined_method_details`, then `method_details`, then the supported flat idea fields, so the narrative describes the method that was actually handed to the experiment backend.

The session-level `ideas.json` and the reduced online-memory record will not be used as substitutes: the former contains multiple candidates and currently retains only refined method details, while the latter intentionally omits parts of the Idea record.

The Markdown projection contains the method title and name from the selected method details, the research hypothesis from `Idea.text`, the motivation from `Idea.rationale`, the baseline context from `Idea.baseline_summary`, and the method overview, novelty statement, and detailed method from `description`, `statement`, and `method`. Scores, critiques, gathered evidence, references, superseded method versions, and evolution records remain in the Research Dossier but are not included in this method-focused input. Empty optional fields omit their headings without replacement text; an empty executed method fails validation before PaperOrchestra runs.

**Considered Options**

- Pass the session-level `ideas.json` directly to PaperOrchestra. Rejected because it mixes candidates and lacks the complete selected idea context expected by the single-paper workflow.
- Ask a model to synthesize `idea.md` from available artifacts. Rejected because synthesis could add or alter scientific claims before PaperOrchestra begins writing.
