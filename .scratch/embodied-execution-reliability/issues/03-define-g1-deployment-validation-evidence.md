# Define G1 deployment-validation evidence

Type: research
Status: resolved
Labels: wayfinder:research
Parent: ../map.md
Assignee: Codex
Blocked by: 01-define-first-embodied-skill-and-task-contract.md, 02-establish-g1-embodiment-and-compatible-policy-baseline.md
Blocks: 04-define-macro-action-safety-and-human-gate.md, 05-define-training-data-and-model-promotion.md

## Question

What layered deployment-validation environment and evidence matrix can conservatively admit the chosen skill from policy evaluation to supervised G1 execution?

The resolution must distinguish optional benchmark validation from G1-specific deployment validation, define the minimum critical-constraint alignment rather than a full digital twin, compare plausible G1 simulation/replay/shadow-mode options against the actual embodiment, and state what simulation evidence can and cannot establish.

## Resolution

Validation is an ordered ladder in `vegapunk/embodied/admission.py`: `policy_evaluation` -> `offline_replay` -> `shadow_mode` -> `hardware_supervised`. Each stage before the target must independently satisfy a minimum attempt count and success rate, and any recorded safety violation withdraws admission outright.

Two properties matter more than the specific thresholds.

Evidence is scoped. An `EvidenceRecord` is valid only for the one skill revision, embodiment digest, and policy digest it was produced on. A benchmark score obtained elsewhere is not evidence about this robot, and there is no code path that lets it become one. `policy_evaluation` can establish software-contract correctness but can never by itself admit hardware, no matter how many attempts accumulate.

Approval is pinned. A `HumanApproval` names the evidence digest it reviewed, so newly recorded evidence invalidates the approval instead of being silently inherited by it. Approvals also expire (8 hours), because approval is a statement about a laboratory situation, not a permanent property of a skill.
