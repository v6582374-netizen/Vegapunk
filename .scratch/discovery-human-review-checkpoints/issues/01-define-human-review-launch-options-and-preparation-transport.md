# Define Discovery Human Review Launch Options and Preparation transport

Type: grilling
Status: in-progress
Labels: wayfinder:grilling
Parent: ../map.md
Assignee: Codex
Blocked by: none
Blocks: 03-define-mas-ranking-feedback-checkpoint.md, 04-define-method-specification-checkpoint.md, 05-define-handoff-checkpoint-before-paperorchestra.md, 07-define-human-review-acceptance-and-rollout-boundary.md

## Question

What are the canonical three boolean launch options for the MAS, pre-experiment method, and pre-PaperOrchestra handoff checkpoints, and how do optional CLI arguments and the Native Desktop Discovery Preparation controls serialize them into the immutable Launch configuration snapshot?
The decision must preserve omitted/false as fully automatic, reset all options to false for every new Launch, avoid a standalone Settings module or per-task policy, and define validation plus the Run request shape without implementing production code.
