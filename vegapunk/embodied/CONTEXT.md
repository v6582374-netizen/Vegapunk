# Embodied Operation Context

## Glossary

**Embodied Operation Harness**:
The bounded system that collects, learns, executes, verifies, and records one
laboratory physical-operation loop under human authority.
It is organized around the robot and instrument's real states, not an
experiment-search workflow.
_Avoid_: discovery harness, candidate-search harness, robot scientist

**Golden Skill**:
The first complete, ordered Instrument Operation Loop used to prove the
Generation process without generalizing across tasks.
_Avoid_: demo segment, skill collection, benchmark clip

**Physical Skill Revision**:
One frozen, human-reviewed statement of a Physical Skill's complete task,
safety, completion, and abort contract.
_Avoid_: mutable skill definition, latest skill, prompt

**Candidate Bundle**:
One immutable policy candidate bound to its training provenance, observation
and action contracts, Physical Skill Revision, embodiment, and configuration.
_Avoid_: checkpoint, model file, policy name

**Campaign Plan**:
The pre-registered ordered evidence ladder and bounded hardware spend for one
Candidate Bundle's Generation Promotion.
_Avoid_: run settings, experiment notes, dynamic schedule

**Generation Promotion**:
The sole authority boundary that validates frozen inputs before any Replay,
simulation, Shadow, or hardware activity may begin.
_Avoid_: deployment, evaluation run, automatic upgrade

**Sealed Rejection**:
The append-only refusal of one Generation Promotion input set, naming the
failed Gate, reasons, and exact input identities that cannot later be replaced.
_Avoid_: exception, failed log line, mutable status

**Whole-Body Target Contract**:
The complete real-time control target published by an upstream policy or
teleoperator and consumed by the existing whole-body tracker and companion
actuators.
For this embodiment it is a root-local motion intent plus a full-body reference
pose and both hand postures, carried as one atomic frame; it holds no global
position, route, object pose, or motor-level command.
_Avoid_: direct joint command, tracker residual action, navigation goal, VLA
output format

**Root Motion Authorship**:
The named owner of the continuously refreshed root intent that carries the
robot to an operating stance, and the observation that closes that loop.
Nothing in the retained stack owns it, so it is an explicit assignment rather
than an assumed capability.
_Avoid_: navigation stack, waypoint follower, elapsed-time arrival

**Instrument State Contract**:
The deterministic monitor that watches an Instrument Operation Loop and may
only hold it.
It gates the loop's single irreversible act and nothing else; the policy flows
through every recoverable transition unsegmented, so this contract never
sequences, authorises, or advances the run.
_Avoid_: state machine driving the robot, step authoriser, gesture list,
intended task plan, per-state success check

**Independent Witness**:
The channel that supplies a gate's evidence from outside the policy's
observation set — preferably the instrument's own report, otherwise a fixed
sensor running a deterministic test on a static scene.
It produces `open`, `closed`, or `indeterminate`; a reading older than its
freshness bound is `indeterminate`, and `indeterminate` holds rather than
either satisfying or failing a gate.
Its pose is part of the scoped configuration.
_Avoid_: policy observation, learned detector, shared camera, confidence score,
last known value

**Episode Outcome**:
A labelled fact about what an episode achieved, established after it ends by a
measurement off the robot.
It scores the run and selects training data; it never gates an action, so no
run waits on it.
_Avoid_: task state, success gate, runtime signal, reward

**Human Testimony**:
A human's recorded account of what they saw during an episode, retained for
failure analysis under its own type.
It is never an observation and can never satisfy a gate.
_Avoid_: observation, ground truth, manual confirmation, operator override

**Reset Record**:
The named human's signed statement of the physical starting state an episode
was collected against — instrument, cup and its starting volume, receiving
vessel, floor and tether.
No software owns reset, and no starting state is inferred from a prior
episode's end.
_Avoid_: automatic reset, assumed initial state, previous episode's final state

**Training-grade Episode**:
One synchronized, provenance-complete teleoperation record of an entire
Instrument Operation Loop, including observations, target contract, state
labels, outcome, and any intervention or abort.
_Avoid_: video clip, successful demo only, partial action trace

**Time Synchronization**:
The named, bounded alignment of observation, Target Bridge, and Independent
Witness clocks for one Training-grade Episode. It makes an observation/target
pair a fact rather than an arrival-order guess.
_Avoid_: implicit timestamps, best-effort timing, camera frame rate

**Training Manifest**:
The frozen list of eligible Training-grade Episodes and every excluded Episode
with its reason. It retains excluded records instead of silently selecting only
successful demonstrations.
_Avoid_: filtered dataset, success-only list, dropped failure

**Qualified Replay**:
The reproducible replay candidate frozen from one eligible Training-grade
Episode. It binds that Episode, control frequency, initial-state envelope and
capture artifact, and carries only validated Whole-Body Targets for the existing
Target Bridge.
_Avoid_: action dump, direct joint playback, actuator shortcut

**Intervention / Abort Record**:
Separate named facts that a normal run was interrupted or ended. They may make
an Episode ineligible, but they never erase its observations, witness readings,
testimony, or outcome.
_Avoid_: failed status, overwritten result, discarded run

**Pilot Batch**:
A deliberately limited collection and training round whose result decides
whether the current task and data contract should scale, change, or stop.
It is not a commitment to a final dataset size.
_Avoid_: production dataset, final benchmark, success-rate claim

**Target Bridge**:
The single component through which any upstream policy or teleoperator reaches
the whole-body tracker and companion actuators.
It owns target validity — shape, bounds, ordering, freshness — and commits a
complete actuation set atomically; nothing may reach an actuator around it.
_Avoid_: Redis key, message queue, action publisher

**Safe Hold Target**:
The target published when commanding authority lapses, expressed per actuator
because the safe direction differs between them.
For the body it is a stand target whose safety does not depend on what the
robot was doing; for the hands it is the last commanded aperture, because
releasing a held object is irreversible.
It is always something published, never the absence of a target.
_Avoid_: stop command, frozen last target, damping, no-op

**Manual Safety Authority**:
The human-operated path that removes actuator torque, outside the target data
plane and outranking everything in it.
No software component may claim to substitute for it, including by reducing
control stiffness.
_Avoid_: software abort, bridge stop, safe hold, policy halt

**Authority Latch**:
The state a lapse of commanding authority leaves behind: motion authority stays
withdrawn until a named human clears it.
Fresh, valid targets do not restore it on their own.
_Avoid_: automatic recovery, retry, transient fault
