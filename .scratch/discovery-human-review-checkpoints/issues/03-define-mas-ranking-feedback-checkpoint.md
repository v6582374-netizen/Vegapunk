# Define MAS ranking/feedback checkpoint contract and presentation

Type: prototype
Status: open
Labels: wayfinder:prototype
Parent: ../map.md
Assignee:
Blocked by: 01-define-human-review-launch-options-and-preparation-transport.md, 02-define-shared-human-review-checkpoint-and-resume-lifecycle.md
Blocks: 07-define-human-review-acceptance-and-rollout-boundary.md

## Question

What exact current-launch seam creates a checkpoint on every MAS entry into `AWAITING_FEEDBACK` after ranking, what read-only candidate/trajectory artifacts are presented, and how does explicit Resume return through the existing MAS session without adding a second feedback-resume action?
The prototype/decision must account for repeated MAS checkpoints, the fact that `ideas.json` may not exist before MAS completion, the Version 1 read-only surface, and the future (out-of-scope) artifact-editing path.
