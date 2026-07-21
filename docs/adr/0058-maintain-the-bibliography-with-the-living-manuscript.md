---
status: superseded by ADR-0077
---

# Maintain the Bibliography with the Living Manuscript

`references.bib` is part of the Living Manuscript from the moment the manuscript is created rather than a raw material reconstructed after Terminal Candidate Selection. After every Agent Task Completion, the same Manuscript Sculptor decides whether the forked context yields, corrects, invalidates, or changes the relevance of literature evidence and, when it does, updates the prose citations and BibTeX entries together. It works from the Sculptor Context Fork, authoritative retrieval artifacts, and current manuscript; Vegapunk will not add a Citation Ledger, bibliography registry, or intermediate projection between them.

Terminal Candidate Selection triggers a global citation review and relevance prune, not a rebuild from the Selected Research Candidate's `Idea.references` and `Idea.evidence`. Sources collected during earlier rounds remain when they support the final research question, baseline, method, comparison, interpretation, or limitations; sources whose only purpose belonged to a discarded candidate are removed with the corresponding prose. Deterministic validation ensures that every cited key exists, every retained entry is cited or deliberately preserved for an unfinished passage, and the bibliography compiles.

The Manuscript Sculptor may format, deduplicate, and correct entries only from authoritative metadata. It may not invent bibliographic fields, characterize a source without retrieved evidence, convert an identity ambiguity into a citation guess, initiate a search, or request metadata enrichment. Under ADR-0059, citation coverage and metadata completeness belong to the research module rather than the writing role.

This supersedes ADR-0012's terminal reconstruction, Selected-Idea-only source boundary, and requirement that a sparse final match set permanently limit the paper. It preserves ADR-0012's prohibition on invented sources and unsupported source characterization while implementing ADR-0050's continuous-sculpting model for citations.

**Considered Options**

- Rebuild the bibliography once from the Selected Idea. Rejected because it discards relevant literature gathered elsewhere in the Discovery Launch and can invalidate citations already integrated into the Living Manuscript.
- Maintain a separate citation ledger and project it into BibTeX. Rejected because the LaTeX bibliography is already the necessary publication artifact and another representation adds synchronization and identity drift.
- Keep every source ever retrieved. Rejected because exploration-specific references would inflate Related Work and obscure the final scientific positioning.
