# Decide the independent harness boundary

Type: grilling
Status: resolved
Assignee: codex
Labels: wayfinder:grilling

## Question

Which current `vegapunk/embodied` concepts remain governing primitives of the
Embodied Operation Harness, and which belong to the discarded discovery-derived
harness and must disappear rather than be adapted?

Resolve ownership at the conceptual boundary first. In particular decide the
fate of intake, adaptation, objective, search, and harness against the
retained safety, execution-loop, embodiment, trajectory, admission, and
hardware-authority concepts. The result must name the smallest public surface
for the new harness without proposing a line-by-line migration.

## Context

The code graph identifies the current execution seam in `loop.py`, `runtime.py`,
`skill.py`, and `hardware.py`; the discovery-derived assembly currently spans
`intake.py`, `adaptation.py`, `objective.py`, `search.py`, and `harness.py`.

The safety envelope has since made the tracker the sole motor executor and
placed the automatic dead-man inside its 50 Hz loop. This decision must
therefore also settle the fate of the retained direct-joint actuation seam —
the `RobotInterface` command/hold pair and the runtimes built on it — which now
describes an authority no component in this embodiment is allowed to exercise.


## Answer

**`vegapunk/operation` is the harness. `vegapunk/embodied` keeps nothing — not
one module, not one class.** The retained *ideas* were re-derived from this
embodiment's physics; none of the code that expressed them survived contact with
it.

### Why the retained execution seam had to go

`embodied` is built on `RobotInterface.command_joint_positions` — a bounded
joint-space move toward a goal pose, with `hold()` as its stop. That shape is
correct for a welded-base arm and wrong for this robot in three ways at once:

- **It commands joints.** On this embodiment the only accepted target is a
  35-value root intent plus 29 joint *references*, consumed by a learned tracker
  that emits the actual joint commands. A component that writes joint positions
  bypasses the thing keeping the robot upright.
- **`hold()` is not a stop.** It is the absence of a command, and on a standing
  biped the absence of a command is the absence of balance.
- **It is goal-directed.** `JointPoseGoal` plus a tolerance describes reaching a
  pose and verifying arrival. This loop has no arrival: root motion is authored
  continuously from vision, and there is no pose gate anywhere in it.

So `runtime.py`, `loop.py`, `skill.py`, `hardware.py`, `adaptation.py` and
`calibration.py` describe an authority no component in this embodiment may
exercise. They are not adapted; they are not what this robot is.

### What became of each retained idea

Every one survives as vocabulary and as a *different* implementation:

- **human motion authority** → `bridge.MotionGrant`, scoped to a configuration
  digest rather than a skill revision, because the room is part of what was
  authorised.
- **deterministic abort** → split in two: `tracker.TrackerLoopGuard`
  (involuntary, inside the 50 Hz loop) and `TargetBridge.hold` (deliberate).
  `SafetySupervisor` was one component; it had to become two, because a watchdog
  in the publisher cannot fire when the publisher is what died.
- **trajectory record** → `episode.EpisodeRecord`, carrying what the old ledger
  lacked: calibration, applied-target alignment, witness value, safety events,
  reset, measured outcome.
- **embodiment verification** → `target.WholeBodyTarget`: verification moved from
  a document comparison to *construction*, so an unexecutable frame cannot exist.
- **evidence-scoped admission** → `ConversionReport.provenance_gaps` plus the
  checkpoint manifest. The four-stage ladder is gone; a dataset is training-grade
  or it is not, and a checkpoint carries the reason it may not be served.

### The discovery-derived assembly is out of scope, not migrated

`intake`, `objective`, `search`, `harness`, `campaign`, `regime`, `bench`,
`simulation`, `fidelity`, `preview`, `store` and `admission` search an adaptation
space for a robot that cannot do something. This loop does not search. It has one
task, one policy, one gate, and a human who decides whether the pilot scaled.

### The smallest public surface

Eleven modules, one import path, 106 exported names, one rule: the only way to a
motor is `TargetBridge`. `vegapunk/embodied` is left untouched and still passes
its own tests. It is not a dependency of anything here.
