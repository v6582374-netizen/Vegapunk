---
status: superseded by ADR-0092
---

# Require Artifact Paths Only for Successful Results

The Dossier Service requires every Discovery result to contain a boolean `success` and non-empty `idea_name`, but requires `folder_name` only when `success` is true. Vegapunk's normal experiment return includes a folder for completed attempts, while exception paths can return a failed result without one; rejecting the whole Discovery Launch for that absence would make PaperOrchestra incompatible unless Vegapunk experiment code were changed.

Failed results without a directory remain valid failure facts for Paper Candidate Round fallback and provenance. They can never enter a successful candidate pool, be selected, or be used as scientific evidence.

**Considered Options**

- Require `folder_name` on every result. Rejected because existing Vegapunk exception results do not guarantee it and Vegapunk source is otherwise read-only for this migration.
- Synthesize or infer a failed Candidate Experiment path. Rejected because scientific artifact association must never be inferred.
