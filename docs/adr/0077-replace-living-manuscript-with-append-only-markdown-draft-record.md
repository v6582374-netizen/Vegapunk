---
status: superseded by ADR-0110
---

# Replace Living Manuscript with an Append-Only Markdown Draft Record

The previous Living Manuscript concept is removed rather than extended. A Discovery Launch instead maintains one launch-local `manuscript/draft.md` Research Draft whose purpose is exhaustive capture of research activity, not a continuously polished or publication-ready paper. Every observable model call, tool call, tool result, error, and completed stage output may append its own self-contained Draft Block in chronological order, including information that appears irrelevant or redundant. Hooks serialize and append these blocks directly without invoking any writing model; structuring, filtering, and conversion into a paper are downstream PaperOrchestra responsibilities.

As soon as a new Launch directory exists, it creates an empty record and activates capture before any Agent, model, tool, or experiment work. The initial research question, prompt, and effective configuration are appended in full before those actions begin. A resumed Launch reopens its existing record at the same lifecycle boundary and appends without truncating, rewriting, or reordering prior blocks.

This supersedes the prior decisions that made a continuously sculpted LaTeX manuscript the automatic Discovery output. No old manuscript or Sculptor terminology should be used to imply an authoring Agent, editorial quality, adaptive paper structure, validation, or terminal-paper synchronization.
