---
status: accepted
---

# Persist Immutable Candidate Selection Provenance

Each Dossier Run persists one immutable `candidate_selection.json` at the Dossier Run root after Terminal Candidate Selection succeeds and before raw-material generation or any writing-model call begins. It records the Paper Candidate Round, round fallback, complete successful candidate pool, comparison criterion and its source, model judgment, excluded candidates, random fallback, and final Selected Research Candidate as applicable.

The mutable `dossier_run.json` remains the operational stage checkpoint, while `candidate_selection.json` is the stable scientific selection record. Resuming the same Dossier Run must validate and reuse the existing selection without reranking, reinference, or rerandomization; intentionally choosing again requires a new Dossier Run ID.

PaperOrchestra supplies the structured selection record directly to the `研究过程` writer and verifies that every required disclosure from ADR-0032 and ADR-0037 appears in the compiled Research Narrative. It will not create an intermediate Markdown selection projection.

**Considered Options**

- Store selection details only inside the mutable checkpoint manifest. Rejected because operational stage updates should not be able to obscure or replace the scientific selection basis.
- Generate a second Markdown rendering for writing agents. Rejected because the structured record can be supplied directly without another potentially lossy restatement.
