# Define shared Human Review Checkpoint and explicit Resume lifecycle

Type: grilling
Status: claimed
Labels: wayfinder:grilling
Parent: ../map.md
Assignee: Codex
Blocked by: none
Blocks: 03-define-mas-ranking-feedback-checkpoint.md, 04-define-method-specification-checkpoint.md, 05-define-handoff-checkpoint-before-paperorchestra.md, 07-define-human-review-acceptance-and-rollout-boundary.md

## Question

What common durable lifecycle contract represents an enabled seam that finishes its current execution, becomes inactive, exposes read-only artifacts, and continues only after one explicit Resume?
The decision must cover CLI and Native adapters, checkpoint files/manifest, state and attempt transitions, restart/reconnect behavior, idempotency, and protection against duplicate experiments, memory writes, baseline changes, or PaperOrchestra handoffs.
