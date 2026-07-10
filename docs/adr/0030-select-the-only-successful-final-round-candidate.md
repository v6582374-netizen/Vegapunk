---
status: superseded by ADR-0031
---

# Select the Only Successful Final-round Candidate

When the last completed Discovery Round contains exactly one Candidate Experiment whose recorded result has `success: true`, PaperOrchestra selects that candidate directly. No primary metric or optimization direction is required because there is no successful alternative to compare, and failed candidates cannot replace it if later Dossier input validation finds incomplete materials.

This is a cardinality rule rather than a scientific ranking rule. Validation of the selected candidate's metrics, reports, and other required artifacts remains the responsibility of Dossier input preparation before any writing model is called.
