# Embodied Instrument Operation map

Type: map
Status: open
Labels: wayfinder:map

> **Supersession notice (2026-08-19):**
> [`spec.md`](spec.md) is the authoritative implementation specification for
> the closed experiment loop. In particular, the task contains no liquid:
> “pour” now means a reversible tilt gesture. Earlier references in this map
> and its tickets to liquid transfer, weighing, a liquid-specific gate, or a
> human reset caused by pouring are historical context, not current design.

## Destination

Produce an implementation-ready specification for a **closed experiment loop**
in which a Unitree G1 with BrainCo Revo2 hands is the instrument and the
laboratory bench task is the science: design a batch of conditions, run them,
judge each one on machine-readable evidence, and let the result change the next
batch. The robot's own competence is the quantity under study — where the loop
succeeds, where it fails, and whether that envelope grows batch over batch.

"Working" therefore means **the loop closes**, not that the robot succeeds once.
A batch of twenty episodes that all fail, each with a witnessed verdict, an
automatic reset and a durable record, is a passing first milestone; a single
unrepeatable success is not.

Within a run the policy is not authorized step by step: a deterministic monitor
gates only the irreversible act on independent evidence of the instrument's
actual state, and anything it cannot establish holds the robot and leaves a
durable record.

The claim under test is falsifiable and does not depend on our being able to
train a model: **a frozen policy can be taken from ~20% to ~80% on a fixed task
by condition search, environment shaping, and invocation tuning alone.** The
loop's action space is everything except the weights (22).

The map ends with a clear build route, not a deployed robot or a trained
policy.

## Notes

- This is an original Embodied Operation Harness. It does not inherit the
  discovery harness's complaint routing, candidate search, objective scoring,
  or MAS workflow.
- COSA is an architectural learning sample, not a component dependency. The
  local copies of its launch statement and V³-0 technical report are in
  [`docs/research/limx-cosa/`](../../docs/research/limx-cosa/).
- The existing low-level whole-body tracker is retained as the sole motor
  executor; its target contract is now established (see Decisions so far). Its
  target-publishing pathway is *not* retained as-is: it has no expiry,
  sequence, acknowledgement, or automatic safe stop, so a target bridge owns
  those before any policy holds motion authority.
- Two wrist cameras exist and belong in the first data contract. A 20-episode
  pilot is the first collection batch; it is a learning experiment with a
  go/no-go decision, not the final dataset-size commitment.
- The instrument state contract observes and holds; it never sequences the run.
  Nothing added to this map may reintroduce per-step authorisation, because that
  rebuilds the scripted point-to-point behaviour the pilot exists to replace.
- The retained reliability primitives — human motion authority, deterministic
  abort, trajectory record, embodiment verification, and evidence-scoped
  admission — constrain the new harness. An LLM/MAS is never in the real-time
  control loop.
- The harness is **built**, in [`vegapunk/operation/`](../../vegapunk/operation/)
  — thirteen modules, 224 tests, and one operator entry point at
  [`scripts/run_operation.py`](../../scripts/run_operation.py). Run
  `python3 scripts/run_operation.py readiness` for the current state of what is
  proven in software versus what waits on a human.
- Two classes of work remain. **Physical**: 02, 12, 15 need hardware, and 05
  and 09 need the pilot data those produce. **The loop layer**: 17-21 are the
  design work that turns a single supervised run into a self-turning batch,
  under the action space and honesty rules settled in 22.
  13, 14 and 16 are deferred with locomotion and the pour.
- **v1 is stationary.** Locomotion is deferred, not cancelled: the contract's
  root channels are commanded zero rather than removed, so adding the approach
  later is a rank increase on an unchanged seam. This deletes the three reasons
  a published tabletop WMA could not be used here (action width, 15 Hz, no
  locomotion) — all three came from the approach.
- Consequently the six existing vendored demonstrations become *on-task* rather
  than off-task: their near-zero net displacement was only a defect against a
  walking target.
- **A predictive node is part of the first loop, not a later upgrade.** It is an
  imagined bench: given a frame and an action sequence it generates the future
  *witness* view — not the egocentric view — so the same witness code that
  judges the real camera also judges the imagined one, and a prediction is
  scored against reality as one bit against one bit. It never judges; the
  witness does. Every batch carries at least one real anchor, and a batch
  without one is recorded as unanchored and may not yield a conclusion.
- The reversible core is the whole task minus the pour: open lid, grasp cup,
  lift, replace cup, close lid. Cup pose is the condition axis, and it is
  visible, measurable and freely resettable. Running the reversible core leaves
  the world as it started, which is what allows a batch to turn without a human
  between episodes.
- **The instrument is mute.** It exposes no state over any interface, so the
  fixed bench camera is not a fallback — it is the only possible witness, and it
  is now load-bearing twice over: it judges the real bench *and* it is the
  yardstick that scores the predictive node. Nothing in the loop layer is
  reachable without it.
- The dividing line on human word: a **gate** authorises an irreversible act
  mid-run and never accepts testimony; an **outcome** labels a finished episode
  and may be judged by eye. Mass is an optional upgrade to outcome precision,
  never a precondition for having a record.
- **Pre-registration is not optional.** A batch's predicted outcome is written
  into the record *before* the batch runs. Without it, "the AI adjusted its plan
  on the results" is after-the-fact narration rather than auditable history, and
  the rising curve is unfalsifiable. Same reason the witness, not a human, gives
  the verdict.
- **A generation is a frozen bench configuration**, and it is a first-class
  concept above the batch. Batches accumulate inside a generation; samples never
  merge across generations, only conclusions may be compared. This exists because
  environment shaping is the loop's strongest lever *and* it destroys the evidence
  already accumulated — so the tension has to be represented rather than papered
  over. Sealing a generation is atomic and deletes nothing.
- **Switching generation is an irreversible act, so it takes independent
  authorisation** — a named human approves it and the approval enters the record
  with who, when, what changed, and where the prior generation is sealed. This is
  the pour gate's rule applied a second time, not a new mechanism: the retired
  evidence cannot be recovered. The loop may not open a generation on its own,
  which also stops it farming the cross-generation curve by tearing the bench down
  repeatedly.
- **The work order is the loop's only output it cannot execute itself.** The loop
  has no hands, so a proposed bench change goes to a human — but the initiative is
  the loop's, and because execution changes the generation stamp, nobody can
  quietly adjust a fixture and leave prior samples looking current. A work order
  must stake its **expected gain**, which is the generation-level
  pre-registration: install the recess, run the new generation's first batch, and
  a wrong work order is wrong in the open.
- **Effectiveness is two curves, and the second matters more.** *Within* a
  generation: success rate rising under condition search and invocation tuning, on
  a field whose shape is fixed — this has a ceiling. *Across* generations: the
  reliable envelope growing through environment shaping, which changes the shape of
  the field itself. The second is the stronger reading of the brief's "improving
  experimental effectiveness".
- **Three loops, three periods, three owners** — conflating them is what made
  earlier rounds of this discussion slide. The *control* loop (20 ms) turns
  inside the tracker. The *training* loop is offline and its object is model
  parameters; locomotion's feedback lives here, entirely inside simulation with
  free reset and ground-truth reward, which is why the cerebellum is the wrong
  home for the brief's loop. The *experiment* loop (per batch) is the one this
  map builds: its object is conditions, fixtures and protocols in the real
  world, and its judge is an instrument.

- Use `grilling`, `domain-modeling`, `codebase-design`, and `research` when
  resolving tickets. The embodied vocabulary lives in
  [`vegapunk/embodied/CONTEXT.md`](../../vegapunk/embodied/CONTEXT.md).

## Decisions so far

- [Define what the loop may change](issues/22-define-what-the-loop-may-change.md) — competence is a *field*, not a number: the model is frozen but our position in its field is not, so the loop's action space is everything except the weights — conditions, environment shaping, invocation tuning, and minimal added data, three of which never touch the model. The falsifiable claim under test is that a frozen policy goes from ~20% to ~80% on this bench by those means alone. Pre-registration is what separates this from theatre. Its four deliverables — an envelope with provenance, fixture/protocol design, a retry policy grown from recorded failures, and a minimal data shopping list — are what a deploying laboratory otherwise obtains by undocumented trial and error.
- [Define the self-turning batch](issues/17-define-the-self-turning-batch.md) and [Define the batch designer](issues/21-define-the-batch-designer.md) carry the loop's skeleton: a **generation** (one frozen bench configuration) sits above the batch, samples never merge across generations, and switching generation is an irreversible act needing a named human's approval — the pour gate's rule applied a second time. The loop's strongest lever, environment shaping, is also the one it has no hands for, so it emits a **work order** staking an expected gain; that expectation is the generation-level pre-registration, which makes "rebuild the apparatus" falsifiable. Effectiveness is two curves: within a generation (ceilinged) and across generations (reshaping the field).

- [Establish the TWIST2 whole-body target contract](issues/01-establish-twist2-whole-body-target-contract.md) — the sole seam a policy may publish is `body[35] + left_hand[6] + right_hand[6]` at 50 Hz behind one atomic, sequenced, expiring target bridge; the neck is a dormant channel and is excluded from the first loop. Note: [research](../../docs/research/2026-08-17-twist2-whole-body-target-contract.md).
- [Define the target-bridge safety envelope](issues/10-define-the-target-bridge-safety-envelope.md) — silence is not safety on a standing biped: safe hold is a positively published stand target for the body and a frozen aperture for the hands, the automatic dead-man lives in the 50 Hz tracker loop rather than the publisher, a trip latches until a named human clears it, and torque removal stays with the Manual Safety Authority.
- [Decide who authors root motion](issues/11-decide-who-authors-root-motion.md) — the policy authors root motion directly from vision; there is no stance-seeking layer, no arrival event and no handover, because nothing in the retained stack reports position. Dead reckoning — integrated velocity, commanded displacement, elapsed time — is never evidence.
- [Define the approach geometry and tether envelope](issues/13-define-the-approach-geometry-and-tether-envelope.md) — one marked start footprint about 2 m out inside a shallow facing cone; continuous visual contact with the phase's target is the corridor rule and losing frame is a hold; the tether enters from behind and never crosses the walked corridor; cable routing and start footprint are part of the scoped configuration.
- [Define the verifiable instrument state contract](issues/03-define-verifiable-instrument-state-contract.md) — the state contract is a monitor whose only authority is hold, not a sequencer: it gates the loop's one irreversible act (the pour) on one bit from an Independent Witness outside the policy's eyes, `indeterminate` holds, and liquid transfer is demoted from a state to an Episode Outcome weighed off the robot after the run.

- [Decide the independent harness boundary](issues/04-decide-the-independent-harness-boundary.md) — the discovery-derived assembly (intake, adaptation, objective, search, harness) is discarded rather than adapted, and the direct-joint actuation seam goes with it: on this embodiment no component may command joints around the tracker. What survives is five ideas, not five files — named motion authority, deterministic hold, scoped evidence, an append-only record, and refusal on missing information — all rebuilt inside `vegapunk/operation`.
- [Choose the minimal policy learning and serving shape](issues/06-choose-the-minimal-policy-learning-and-serving-shape.md) — COSA's fast/slow split is adopted; its flow-matching fast policy and reward model are not. A learned producer must *project* its continuous output onto the feasible set before the contract sees it, because unbounded regression lands outside a joint range by construction, unlike a hand-authored frame where the same value is a bug.
- [Define the verified execution and trajectory boundary](issues/07-define-the-verified-execution-and-trajectory-boundary.md) — the frame is judged before publication, never after, and every tick writes exactly one record including a held one. A producer that raises is treated as one that produced nothing, at both layers: an exception in a balance loop is the failure mode the dead-man exists to remove.
- [Plan the harness replacement](issues/08-plan-the-harness-replacement.md) — the replacement is additive: `vegapunk/operation` was built alongside `vegapunk/embodied` rather than migrated out of it, so the cutover is reversible by deletion and no existing test changed.

## Not yet specified

- The exact variation envelope for later data collection: initial robot pose,
  cup pose, lighting, camera occlusion, liquid volume, and workspace changes.
- Whether the head camera's body-locked view is sufficient for the approach it
  must guide, or whether the dormant neck becomes load-bearing sooner than
  planned.
- Who handles the tether during a run, and whether a handler standing behind
  the robot is an operator role with its own stop authority.
- The post-pilot scale decision: extend the dataset, revise the task/data
  contract, or abandon the first learning formulation.
- Whether the neck channel is later commissioned as a verified actuator under
  the same target envelope, and what active head aiming would then buy.
- How the operator hands control to and takes it back from the policy during a
  run, given that a latched hold is cleared by a named human.
- The batch-level stopping rule's constant: how many consecutive holds mean the
  batch is chasing a defect rather than sampling an envelope.
- Whether v1 fixes the robot to a stand, trading stance fidelity for removing
  the fall mode outright.

## Out of scope

- Reusing the discovery harness, UCT adaptation search, objective scoring, or
  MAS candidate-generation workflow as the embodied harness.
- Training a new whole-body tracking/balance foundation model.
- Direct policy-to-joint control that bypasses the existing tracker.
- A separate SLAM/map/path-planning navigation stack for the first loop.
- COSA-scale fast/slow VLA, a reward model, or real-robot RL: reinforcement
  learning presupposes a policy that already works, so it stays out until a
  supervised policy has a measured success rate.
- Whole-body locomotion in v1 — deferred to a later rank increase, not removed
  from the destination.
- A hand-built physics twin of the instrument, unconstrained language-to-motor
  control, or generalization claims beyond the defined instrument loop. The
  predictive node is learned from real episodes and scored every batch; it is
  not a modelled twin and it is never allowed to conclude.
