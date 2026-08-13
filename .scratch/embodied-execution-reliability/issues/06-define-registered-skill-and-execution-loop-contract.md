# Define the registered skill and execution-loop contract

Type: grilling
Status: resolved
Labels: wayfinder:grilling
Parent: ../map.md
Assignee: Claude
Blocked by: none
Blocks: 03-define-g1-deployment-validation-evidence.md, 04-define-macro-action-safety-and-human-gate.md, 05-define-training-data-and-model-promotion.md

## Question

What common contract must every selectable, already implemented Physical Skill satisfy so that the Version 1 system can execute a complete governed loop without depending on natural-language task interpretation?

The decision must distinguish a Skill Definition from one Skill Run, determine the minimum inputs and version identity, preconditions and postconditions, automatic and human verification, hard-failure semantics, the relationship to a VLA policy, and whether the initial catalog contains deterministic skills, VLA-driven skills, or both.

## Resolution

**Skill definition vs. run.** `vegapunk/embodied/skill.py` separates three things: a `PhysicalSkill` is an immutable, revision-identified contract; a `SkillSelection` is one bound, reproducible request carrying no execution state; a run is what the loop produces. Keeping the request separate from the run means a request can be recorded, reviewed, and compared before any hardware activity exists.

**Parameters are closed by construction.** A `ParameterSpec` must declare either an allowed set or both numeric bounds. An unconstrained physical input would let a caller widen behaviour without a contract revision, so it is rejected at definition time rather than at execution time.

**Identity is a digest, and the registry is append-only.** Revisions accumulate instead of overwriting, so recorded evidence keeps pointing at the exact contract that produced it. Re-registering a revision with a different contract is an error.

**Both kinds, mutually exclusive.** The catalog holds `deterministic` and `vla` skills. A VLA skill must name the checkpoint it was validated against; a deterministic skill must not carry one. Allowing both would blur which component authored the motion.

**The loop is a fixed order** (`vegapunk/embodied/loop.py`): quarantine -> compatibility -> admission -> preflight -> supervised motion -> postcondition verification -> trajectory. Cheap deterministic refusals come first, so a configuration that can never be admitted is rejected before a human is asked to stand next to a moving robot.

**Hard failure is defined by what it forbids.** Every abort quarantines its configuration, including a human stop: a person who intervened is owed a review before the same configuration runs again. Automatic retry after an abort is precisely how a one-off becomes a pattern. Only a named human clearance lifts it. A failed postcondition is *not* a hard failure -- the skill simply did not work.

**Verification cannot be waived.** A postcondition the runtime does not measure is a failed verification, not a pass, so a blind sensor cannot be mistaken for a working skill.

**The loop bounds itself.** Every supervisor time check reads elapsed time from the runtime, so a frozen runtime clock would defeat all of them. The loop therefore derives its own control-step ceiling from the embodiment's declared frequency and aborts on it.

**Actuation sits behind one protocol** (`SkillRuntime`: observe, start, step, abort, postconditions). A deterministic controller and a VLA policy runner both implement it, which is why the loop's guarantees do not depend on which is in use. `observe` is separate from `step` so preflight can look without commanding motion.
