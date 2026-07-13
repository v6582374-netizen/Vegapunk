---
status: superseded by ADR-0058
---

# Use InternAgent Citation Evidence without Paper-stage Search

The initial PaperOrchestra integration will derive its complete citable collection from the Selected Research Candidate's `Idea.references` and `Idea.evidence` and will not perform online literature search during a Dossier Run. A deterministic renderer joins records by normalized DOI and otherwise by exact normalized title, then emits the same matched set as `references.bib` and `citation_map.json`. It may format and deduplicate explicit metadata but may not use fuzzy matching, call a model to repair records, or add authors, dates, abstracts, venues, or identifiers.

Only records with both reference metadata and corresponding evidence content enter the citable collection. Unmatched records remain available in the Research Dossier but cannot be cited by PaperOrchestra. If the matched collection is sparse, the Research Narrative must remain correspondingly limited instead of silently searching for or inventing additional sources. This reuses InternAgent's completed academic retrieval work, keeps the paper-stage citation set reproducible, and avoids a second provider-specific retrieval path.

PaperOrchestra's literature component retains only its Introduction and Related Work writing responsibility. It consumes the prebuilt citation map and bibliography together with the outline, idea, and experimental log, and may choose among those approved citation keys while composing prose. Its discovery, retrieval, metadata enrichment, bibliography generation, and fixed minimum-citation-ratio behavior are bypassed; it may neither create a new citation key nor trigger a supplemental search when the collection is small.

**Considered Options**

- Let PaperOrchestra repeat its online literature discovery during every Dossier Run. Rejected because it can produce a different citation set from the evidence collected during discovery and introduces additional external dependencies.
- Emit every `Idea.references` record to BibTeX even when no evidence content is available. Rejected because PaperOrchestra's writing and refinement agents would lack the supporting abstract or content needed to characterize those sources reliably.
