# Define training data and model promotion

Type: grilling
Status: resolved
Labels: wayfinder:grilling
Parent: ../map.md
Assignee: Codex
Blocked by: 01-define-first-embodied-skill-and-task-contract.md, 02-establish-g1-embodiment-and-compatible-policy-baseline.md, 03-define-g1-deployment-validation-evidence.md, 04-define-macro-action-safety-and-human-gate.md

## Question

What data contract, offline fine-tuning trigger, held-out evaluation, historical replay requirement, shadow validation, review, rollback, and supervised-release rule govern a laboratory-adapted VLA candidate?

The decision follows the current direction: a public general checkpoint is the baseline; high-quality demonstrations plus real success/failure trajectories create a governed dataset; Version 1 records training-ready evidence and designs the interface but does not autonomously train or promote a model from individual hardware runs.

## Resolution

`vegapunk/embodied/trajectory.py` records what a run leaves behind, deliberately separate from the loop: the loop decides what happens to the robot, the ledger decides what the organisation is allowed to conclude afterwards.

**Every exit is recorded, including a refusal.** A run that was prevented is information about the system. Refusals are marked non-attempts so they never dilute a success rate, and they cannot carry runtime observations.

**Training evidence is earned, not collected.** A trajectory enters a `TrainingManifest` only when its outcome was confirmed by a named human, its observation stream is complete, its embodiment is fully verified, and it came from `shadow_mode` or `hardware_supervised`. Benchmark-stage runs are excluded from a hardware dataset by construction. Confirmed **failures are kept** -- a labelled failure is data; an unlabelled success is not. Every exclusion is retained with its reason so a smaller-than-expected dataset can be explained rather than guessed at.

**Admission evidence is derived, not typed in.** `derive_evidence` summarises a scope's runs into an `EvidenceRecord`, so an abort on hardware withdraws admission by arithmetic instead of by someone remembering to file it. Only envelope, time-limit, and stale-observation aborts count as safety violations; a human stop is a hard failure but not a violation of the envelope.

**Manifests are digest-identified**, so a future fine-tune cites an exact trajectory set and a changed set is a different dataset.

Version 1 stops here by design: it records training-ready evidence and defines the interface, but does not train, evaluate, or promote a model. No hardware run updates weights.
