---
status: accepted
---

# Ingest Large Research Drafts in Block-Aligned Batches

PaperOrchestra does not place the complete, indefinitely growing Research Draft into one model request. At the beginning of a PaperOrchestra Run it reads `draft.md` in context-sized batches aligned to the existing `<!-- draft-block -->` boundaries and derives paper-working material covering claims, results, formulas, citations, failed attempts, decisions, and artifact paths. Those derived files live only inside the PaperOrchestra Run, are checkpointed as PaperOrchestra work, and may be regenerated from the canonical Draft and Launch artifacts.

Outline, plotting, literature, section-writing, and refinement stages consume this working material and may return to the corresponding raw Draft blocks or authoritative Launch artifacts when more detail is required. Nothing in this ingestion step rewrites, truncates, filters, or replaces `draft.md`, and Discovery does not prepare a second handoff representation.

This supersedes the inherited assumption that the complete idea and experiment log can always be concatenated into one Outline Agent request. Without block-aligned ingestion, exhaustive Draft capture would eventually exceed every finite model context window and prevent PaperOrchestra from starting.

**Considered Options**

- Truncate the Draft to fit one request. Rejected because later or earlier research evidence could disappear silently.
- Add a Discovery-side summary or raw-material conversion layer. Rejected because Draft Handoff passes the canonical raw material directly and PaperOrchestra owns its interpretation.
- Require the entire Draft to fit the configured model context. Rejected because Draft size grows with observable research activity and is intentionally unbounded.
