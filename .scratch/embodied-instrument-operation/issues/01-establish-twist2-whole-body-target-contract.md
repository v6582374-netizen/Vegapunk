# Establish the TWIST2 whole-body target contract

Type: research
Status: resolved
Assignee: Hubble
Labels: wayfinder:research

## Question

What exact real-time target contract can a learned policy publish into the
existing TWIST2 tracker on this machine, and which parts are demonstrated
rather than merely present in source code?

The answer must establish the complete body, BrainCo Revo2 hand, and neck
target channels; their cadence, state feedback, authority and stop semantics;
the source of root motion; and the recording fields that preserve the
demonstration. It must distinguish a fully connected execution path from
dormant or incomplete code. The output is a primary-source research note and
one recommendation for the sole policy-to-actuation seam.

## Context

The repository's governed execution boundary currently centers on
`ExecutionLoop`, `SkillRuntime`, `RobotInterface`, `PhysicalSkill`, and
`MotionAuthority`. Those modules are indexed without recorded coverage gaps.
The machine also contains a TWIST2 checkout and demonstrations, but it is not
part of this repository index; inspect its source directly and cite it.

## Answer

Research note: [TWIST2 全身跟踪目标契约](../../../docs/research/2026-08-17-twist2-whole-body-target-contract.md).
All findings are cited to first-party source in the machine-local TWIST2
checkout (`master` at `39a6b6c6`, with uncommitted BrainCo edits), not to
secondary write-ups.

### The contract a policy may publish

`body[35] + left_hand[6] + right_hand[6]`, at the tracker's 50 Hz control
period. Nothing else is a demonstrated channel.

`body[35]` is `root v_x, v_y` (root-local), root height `z`, root roll/pitch,
root yaw *angular velocity*, then 29 body joint reference positions in G1
order (legs 6+6, waist 3, left arm 7, right arm 7). Training config, the
online retargeter, the offline motion server and the real deployment all
agree on this layout.

Each Revo2 hand takes six position targets, `[thumb, thumb_aux, index,
middle, ring, pinky]`. The real path slices to six; the historical
seven-value arrays in the teleop producer and old episodes are an obsolete
producer ambiguity and are not part of the contract.

The tracker consumes `127 × 11 + 35 = 1432` floats and emits 29 residuals
that become G1 position-PD targets. The shipped `twist2_1017_20k.onnx`
confirms `[batch,1432] → [batch,29]`. A policy therefore publishes a
*motion reference*, never the 29 residuals and never torques.

### What is dormant rather than connected

- **Neck.** `action_neck[yaw,pitch]` is produced and recorded, and the real
  tracker JSON-decodes it — then never uses it. No neck wrapper, DDS command,
  or feedback publisher exists in the checkout; the first-party neck doc
  defers its controller to an unavailable onboard repo. Excluded from the
  first closed loop's success criteria.
- **Joystick root velocity.** Computed in the teleop state machine, never
  injected into the emitted target.
- **Navigation.** No localization, mapping, waypoint following, or
  vision-to-goal path exists anywhere in TWIST2. Root motion is a
  continuously refreshed *local* kinodynamic intent; there is no route API to
  reuse.
- **Safety semantics.** No TTL on the Redis values, no sequence, no
  acknowledgment, no target-freshness watchdog, and `env.close()` resolves to
  `exit()` rather than a damping command. The teleop "emergency stop" kills a
  stale filename that is not the launched server. The documentation's damping
  statement is not evidence about this checkout.

### The recommended seam

One atomic, sequenced, expiring `TrackerTarget` published through a single
target bridge, which validates freshness, shape, bounds and authority before
writing the complete actuation set; and one `TrackerState` carrying
`sequence`, `state_time_ns`, and `applied_target_sequence` so observations and
actions can be aligned. `TrackerTarget` is a contract recommended here, not an
existing TWIST2 class: the four independent Redis keys become hidden
implementation detail behind it.

Available feedback today is body `[angular_velocity(3), roll_pitch(2),
joint_position(29)]` plus six measured positions per hand. Neck state and
`t_state` are read but never published — every stored episode has them `null`.

### Evidence status of the six local episodes

They prove the image + body + hand record path has run against the physical
instrument scene at 30 Hz. They do **not** establish autonomous navigation, a
learned policy, a task-success label, or a neck loop. The recorder carries
static generic text and no calibration, target sequence, applied action,
safety event, phase, object state, or outcome label — an observation/action
trace, not yet a training or evaluation contract.
