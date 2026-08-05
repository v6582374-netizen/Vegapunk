# Map current-launch integration boundaries for the three checkpoints

Type: task
Status: open
Labels: wayfinder:task
Parent: ../map.md
Assignee:
Blocked by: none
Blocks: 07-define-human-review-acceptance-and-rollout-boundary.md

## Question

Which exact functions, files, artifacts, and resume paths in the current CLI Discovery and Native Desktop sidecar must be adapted for the three checkpoint contracts, and which existing lifecycle/persistence seams can be reused without changing MAS, ExperimentRunner, or PaperOrchestra internals?
This ticket is a bounded contract-mapping task for the implementation plan, not production implementation; it must identify the normal and resume-complete CLI paths plus the Preparation/Launch transport and GUI status surfaces.
