# Define pre-PaperOrchestra handoff checkpoint contract and presentation

Type: prototype
Status: open
Labels: wayfinder:prototype
Parent: ../map.md
Assignee:
Blocked by: 01-define-human-review-launch-options-and-preparation-transport.md, 02-define-shared-human-review-checkpoint-and-resume-lifecycle.md
Blocks: 07-define-human-review-acceptance-and-rollout-boundary.md

## Question

What exact current-launch seam creates one checkpoint per Launch after Discovery has completed and written its summary but before PaperOrchestra starts, and which aggregate read-only candidates, metrics, reports, and provenance does the user see before pressing Resume?
The decision must cover the normal terminal path and already-completed resume path, prevent PaperOrchestra from starting before Resume, and keep Version 1 as inspection plus Resume rather than candidate editing or an internal PaperOrchestra pause.
