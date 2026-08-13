# Establish the G1 embodiment and compatible policy baseline

Type: task
Status: resolved
Labels: wayfinder:task
Parent: ../map.md
Assignee: Codex
Blocked by: none
Blocks: 03-define-g1-deployment-validation-evidence.md, 04-define-macro-action-safety-and-human-gate.md, 05-define-training-data-and-model-promotion.md

## Question

Which exact G1 embodiment, end effector, camera layout, control authority, and compatible VLA checkpoint form the baseline for this effort?

This task produces a factual compatibility inventory. It must establish whether the actual G1 matches the public `g1_dex1` path or needs a laboratory-adapted checkpoint and data collection. It must not map the current LIBERO action representation directly to G1 control.

## Resolution

Compatibility is treated as declared data that must be verified, never as something inferred at runtime. `vegapunk/embodied/embodiment.py` makes an `EmbodimentProfile` (the robot as it actually is) and a `PolicyCheckpoint` (what a checkpoint was trained for) two separate records, and `assess_policy_compatibility` reports one finding per mismatched fact so the output is an adaptation plan rather than a yes/no.

Two facts forced the conservative shape. The upstream loader selects its action/state constants by matching text in the launch command and silently falls back to a 23-dimensional end-effector mode, so the published contract is recorded here explicitly as `UNIFOLM_VLA_BASE_G1_DEX1_JOINT` (25x16 joint mode, bounds normalization, Dex1-1, onboard image service, CC-BY-NC-SA-4.0). And an unverified fact is a mismatch, not an assumption: `unverified_fields` on either side yields `adaptation_required`.

Both sides produce a digest, and every piece of downstream evidence and every trajectory carries it. This is the mechanism that stops a result obtained on one end effector from being read as evidence for another.

Not resolved by this work: the laboratory G1's actual end effector, camera layout, and control authority are still an unverified inventory. A human must fill in the real profile and empty `unverified_fields` before any admission is possible.
