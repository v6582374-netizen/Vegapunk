---
status: accepted
---

# Pass the Draft and Launch Directly to PaperOrchestra

Draft Handoff passes PaperOrchestra the absolute `manuscript/draft.md` path, the absolute Discovery Launch root, and the optional Terminal Candidate Selection path. Discovery no longer converts one Selected Candidate into `idea.md`, `experimental_log.md`, `citation_map.json`, `references.bib`, or `figures/info.json` before PaperOrchestra starts. PaperOrchestra owns any internal extraction, indexing, working copies, or structured materials inside its own run directory.

This removes the lossy selected-candidate raw-material layer and lets PaperOrchestra use its orchestration logic over the full non-structured Draft and available Launch artifacts.
