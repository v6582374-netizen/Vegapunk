---
status: superseded by ADR-0033
---

# Use Explicit Task Metrics for Paper Candidate Selection

Provisionally, when PaperOrchestra must compare multiple successful Candidate Experiments from the Paper Candidate Round defined in ADR-0031, it will read the existing launch-level `prompt.json` and use only `metrics.primary` together with `metrics.optimization_direction`. It will compare the corresponding measured candidate result directly and will not use Vegapunk's averaged `overall_improvement_rate`, ask a model to identify a metric, infer direction from the metric name, or fall back to the first available metric.

This proposal does not authorize any change to Vegapunk's task definitions or generated artifacts. Behavior for a single successful candidate, missing structured metric metadata, missing candidate metric values, and ties remains unresolved. ADR-0023 therefore remains in force until this proposal and its boundary cases are accepted as a complete selection rule.

**Considered Options**

- Reuse the existing maximum `overall_improvement_rate`. Not recommended because the current calculation averages raw metric changes without respecting minimize versus maximize direction.
- Infer the primary metric or direction. Rejected because inferred scientific selection criteria violate the explicit-evidence requirement.
