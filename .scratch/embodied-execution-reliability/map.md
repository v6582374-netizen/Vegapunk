# Embodied Execution Reliability map

Type: map
Status: resolved
Labels: wayfinder:map

## Destination

Produce an implementation-ready decision and architecture specification for a Vegapunk Embodied Execution Profile: a user submits a constrained natural-language physical-operation task; MAS prepares and iterates execution candidates; a compatible VLA produces action candidates; a G1 deployment-validation path admits only evidence-backed macro actions to supervised hardware execution; trajectories become governed memory and future fine-tuning evidence.

The route determines whether and where VLA, world models, and causal models belong. It is planning-only and does not implement production code or command a robot.

## Notes

- Domain: Unitree G1 physical-operation execution under human supervision, initially using a constrained skill directory rather than arbitrary language-to-motor control.
- Consult `grilling`, `domain-modeling`, `codebase-design`, and `research` when resolving tickets. The canonical project glossary is `CONTEXT.md`; an embodied glossary should be created only as terms are resolved.
- Current user direction: reuse Vegapunk MAS as a slow multi-agent harness for candidate generation, simulation evidence, feedback analysis, and iteration. Do not use MAS or an LLM as a real-time motor controller.
- Current user direction: reuse run lifecycle, artifacts, loop, memory, and human gates; do not require the literature-search or paper-generation paths for embodied execution.
- Current user direction: validate candidates in a layered path. LIBERO may be used as an optional benchmark/software-contract environment, but is not evidence that a G1 action is safe. The G1 deployment-validation environment should align critical constraints rather than attempt a full pixel-perfect laboratory digital twin; real-data shadow mode precedes supervised physical execution.
- Current user direction: a physical macro action may run to completion on hardware after preflight and approval, but a deterministic Safety Supervisor retains abort authority at every instant.
- Current user direction: start with a general checkpoint as a baseline; collect high-quality demonstrations and real success/failure trajectories; only introduce offline candidate fine-tuning after data and evaluation justify it. Candidate models require offline evaluation, G1 validation, shadow mode, and human review before supervised hardware admission.

## Decisions so far

All six tickets are resolved. Version 1 is implemented in `vegapunk/embodied/` as six governance modules, each refusing a different way a physical run can be wrong, plus `runtime.py`, the deterministic actuation boundary that is the only thing that moves.

Four further modules supply what the ladder demanded but could not invent -- an environment to run in, a check that the environment is what it claims, a measurement of how fast this robot may be commanded, and an iteration driver -- and one composes them into something a person can run:

- `simulation.py` -- a welded-base MuJoCo G1 presented as a `RobotInterface`, with the three GUI camera views rendered from the model. It measures what physics can measure and refuses to invent the room facts a supervisor checks.
- `fidelity.py` -- whether an environment is the configuration its evidence would be scoped to. A cadence, joint set, end effector, control authority or camera key that disagrees makes the environment unusable rather than merely suspect.
- `calibration.py` -- the command rate is a measurement, not a setting. A probe commands one fixed motion at each candidate rate and reports the peak velocity, the servo's tracking lag, and its resting droop; the ladder admits the fastest rate whose measured peak fits the envelope.
- `campaign.py` -- turns varied, seeded, bounded-perturbation runs into one stage's evidence, and tallies nothing itself: the trajectory ledger counts the outcomes and `admission` decides what they opened.
- `bench.py` -- the assembly. Measure, fix the goal tolerance from that measurement, then iterate `policy_evaluation` and `offline_replay` in ladder order, halting at the first result that makes the next step meaningless.
- `preview.py` -- streams the simulated cameras over the GUI's existing unauthenticated WebRTC camera contract, so a simulated run is watched with the same panel that watches a real G1.

`scripts/run_embodied_bench.py` runs the inner loop end to end on the real MJCF scene and prints what still blocks hardware; `--watch` streams the cameras while it runs. 323 tests in `tests/embodied/`.

- [Define the initial registered-skill boundary](issues/01-define-first-embodied-skill-and-task-contract.md) — a selectable catalog of already implemented Physical Skills; natural language is not a Version 1 execution input.
- [Define the registered skill and execution-loop contract](issues/06-define-registered-skill-and-execution-loop-contract.md) — `skill.py`, `loop.py`: revision-identified contracts with closed parameters, definition separated from run, one fixed ordered path to motion, hard failure defined by what it forbids.
- [Establish the G1 embodiment and compatible policy baseline](issues/02-establish-g1-embodiment-and-compatible-policy-baseline.md) — `embodiment.py`: compatibility is declared data that must be verified; unverified is a mismatch, not an assumption.
- [Define G1 deployment-validation evidence](issues/03-define-g1-deployment-validation-evidence.md) — `admission.py`: a four-stage ladder where evidence is scoped to one configuration and approval is pinned to the evidence digest it reviewed.
- [Define macro-action safety and the human gate](issues/04-define-macro-action-safety-and-human-gate.md) — `safety.py`: a deterministic supervisor with preflight and instantaneous abort authority; advice may only tighten.
- [Define training data and model promotion](issues/05-define-training-data-and-model-promotion.md) — `trajectory.py`: append-only run memory, quarantine after any abort, and training eligibility that must be earned.

### The load-bearing invariants

Stated once here because they are the point of the whole profile:

- Nothing outside `safety.py` can widen an envelope, remove a check, or override a human stop.
- Missing information is unsafe. A stale observation aborts; an unobservable precondition fails preflight; an unmeasured postcondition fails verification.
- Evidence and approval are scoped to one skill revision, one embodiment digest, and one policy digest. A result obtained elsewhere cannot become evidence about this robot.
- Every abort quarantines its configuration until a named human clears it. There is no automatic retry.
- Every exit writes exactly one trajectory record, including a refusal.
- A trajectory becomes training data only with a human-confirmed label, a complete stream, a verified embodiment, and real-robot provenance.

## Not yet specified

Version 1 is a governance skeleton, deliberately complete on the reliability axis and deliberately empty on the physical one. What remains is not design work but laboratory work:

- **The real embodiment inventory.** A human must record the actual G1 end effector, camera layout, control authority, and control frequency, and empty `unverified_fields`. Until then every admission correctly refuses.
- **A hardware `RobotInterface` adapter.** `runtime.py` supplies the first `SkillRuntime`: `DeterministicJointRuntime` drives registered `JointPoseGoal` targets in bounded joint steps, needs no checkpoint, and makes the loop end-to-end testable. What remains is the G1 SDK adapter behind `RobotInterface` (read sensors, command joints, hold) and the reviewed goal poses themselves, which are laboratory measurements rather than design work.
- **The `shadow_mode` environment.** `offline_replay` now has one: the MuJoCo G1, checked against the scope it reports into. `shadow_mode` does not, and it cannot be simulated by construction -- it replays real observations beside a real robot that is not being commanded, so it needs the hardware adapter first.
- **Threshold calibration.** 10 attempts, 90% success, and an 8-hour approval window are defensible defaults, not measured ones. They should be revisited against the first real evidence, and they are single named constants for exactly that reason. The command rate is no longer among them: `calibration.py` measures it, and the velocity margin and tolerance margin that remain are the two named constants left to move.
- **The MAS candidate-preparation path.** MAS can propose selections and tightening advice today; the agent-facing surface that does so is not built.
- **Fine-tuning execution.** `TrainingManifest` defines what a training run may cite. Nothing trains, evaluates, or promotes a model.
- **A policy runtime.** `bench.py` drives the deterministic runtime and refuses a VLA skill outright, because substituting one controller for another would file evidence about this controller under a checkpoint's digest. A `SkillRuntime` that consults a checkpoint is the next component the ladder has room for, and it changes nothing above it.
- **A task with contact.** The reviewed goal is a free-space joint pose, so no evidence collected so far says anything about grasping. The contact facts `fidelity.py` lists as unrepresentable are exactly the ones a manipulation skill would depend on.

## Out of scope

- Directly mapping the current LIBERO 8-by-7 action representation onto G1 joint control.
- Treating a LIBERO benchmark score as proof of G1 safety or sim-to-real success.
- Autonomous online weight updates from individual hardware runs.
- Unconstrained natural-language-to-motor control.
- Real-time MAS/LLM control in a motor-control loop.
- Building a full laboratory digital twin or doing pixel-perfect visual simulation in Version 1.
- World-model or causal-model implementation in Version 1 before a concrete unmet prediction/causal-decision need and appropriate data are demonstrated.
