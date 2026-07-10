---
status: accepted
---

# Randomly Select When No Success Is Comparable

For the initial integration, if a Paper Candidate Round contains multiple successful Candidate Experiments but none has a finite value for the established primary metric, PaperOrchestra randomly selects one of those successful candidates instead of introducing another backward-search or metric-repair mechanism. It never includes failed candidates in this fallback.

The Dossier Run persists the successful candidate pool, the absence of comparable values, the fact that random selection was used, and the selected candidate before writing begins. Resuming the same Dossier Run reuses that recorded selection rather than drawing again. Candidate Selection Provenance and the Research Narrative must disclose that the paper subject was selected randomly because the intended metric comparison could not be performed.

**Considered Options**

- Search earlier rounds for a comparable candidate. Deferred because that adds another fallback branch before this edge case has occurred in practice.
- Infer or synthesize missing metric values. Rejected because no model judgment can replace an unreported experimental measurement.
