---
status: accepted
---

# Allow Model Judgment Only at Terminal Candidate Selection

Terminal Candidate Selection runs once after every Discovery Round has finished and after the Paper Candidate Round has been determined. It first uses any existing structured `prompt.json.metrics.primary` and `metrics.optimization_direction` values unchanged. If either field is absent, PaperOrchestra may use the unified InternAgent model to infer only the missing primary metric, optimization direction, or both from the existing prompt text and the metric names actually reported by the candidates.

This is a narrow exception to the no-inference rule. The model judgment cannot participate in InternAgent's between-round baseline choices, alter a completed Discovery Round, compare candidates across rounds, run during paper writing or refinement, search external sources, or fill any other missing scientific content. A backward fallback to an earlier Paper Candidate Round does not move the judgment into that historical round; the inference still occurs only once at the terminal post-discovery stage.

Any inferred field must be validated against the available candidate metrics and recorded as Candidate Selection Provenance. ADR-0052 governs whether that provenance is scientifically relevant to the manuscript; recording it does not require manuscript disclosure. This supersedes the narrower proposed rule in ADR-0029; behavior when a candidate does not report the selected metric, when inference cannot produce a valid criterion, and when values tie remains separately unresolved.

**Considered Options**

- Permit model judgment during each Discovery Round. Rejected because it would change InternAgent's experiment evolution rather than complete only the missing final convergence.
- Infer other missing paper content during the same call. Rejected because the exception exists solely to make terminal candidate comparison possible.
