---
status: superseded by ADR-0110
---

# Harvest Draft Material at Semantic Task Boundaries

Research Draft candidates come only from Semantic Research Outputs produced by high-level Discovery tasks: hypothesis generation, survey synthesis, reflection, evolution, method development, refinement, and experiment analysis. Literature or experiment-tool information is eligible only after a high-level task adopts it as a scientific conclusion, measurement, citation, limitation, or negative finding.

Generic model requests and responses, tool calls and raw results, logging, standard output, standard error, retries, and transport telemetry no longer append automatically to the Research Draft. These low-level seams lack the domain context needed to distinguish an Artifact Gap from duplicated inputs or operational noise; filtering them after capture would preserve the unbounded growth that the new Draft contract is intended to remove.

This supersedes ADR-0078's direct event append mechanism, ADR-0081's runtime-wide event boundary, ADR-0085's model-context capture contract, ADR-0090's at-least-once event capture, and the corresponding low-level capture assumptions in ADR-0091. It does not yet decide whether eligible task outputs are stored verbatim or projected into a smaller material record.

**Considered Options**

- Keep the generic capture hooks and add content filters. Rejected because the model, tool, and logging layers do not know whether content fills an Artifact Gap.
- Capture everything and classify it at Draft Handoff. Rejected because the full runtime transcript would still grow without a useful bound before classification.
