# Define the verified execution and trajectory boundary

Type: grilling
Status: resolved
Assignee: codex
Labels: wayfinder:grilling
Blocked by: 01, 03, 04, 10

## Question

How do the learned policy, target publisher, deterministic supervisor, and
instrument-state ledger divide responsibility so a failed transition holds the
robot, cannot silently continue, and becomes one durable training/evidence
record?

Resolve authority, preflight, monitoring cadence, transition authorization,
abort/hold behavior, human intervention, record identity, and the treatment of
partial or corrupted episodes. The result must retain the existing safety
invariants without preserving the discovery harness's control model.

## Answer

**Four owners, one ordered path, and no shared state between them.** Resolved by
building it: `vegapunk/operation/session.py` is the composition, and it is the
only object in the package that runs a loop.

One tick, in order:

    observe -> produce -> monitor -> publish -> record

The order is the whole answer. The frame is judged *before* it is published,
never after, so a vetoed pour is a frame the robot never received rather than
one it received and was subsequently told about.

### The division

| Owner | Authority | Cannot |
| --- | --- | --- |
| `PolicyServer` | produce a frame per tick | reach a transport; decide anything |
| `InstrumentMonitor` | veto one class of frames | publish, advance, retry, sequence |
| `TargetBridge` | authority, ordering, freshness, atomic commit, latch | remove torque; fire when itself dead |
| `TrackerLoopGuard` | the involuntary hold, inside the 50 Hz loop | know what a run or a task is |
| `EpisodeWriter` | the durable record | cause anything |

The monitor cannot publish and the bridge cannot judge a posture. Neither holds
task state, so neither can drift into being the sequencer.

### Preflight is the grant, not a checklist

Motion authority is a `MotionGrant`: a named human, a statement, and a
configuration digest. It is a value someone constructed, not a flag, and it is
scoped to the room -- re-routing the tether or moving the witness changes the
digest and therefore withdraws the grant. A missing grant is the normal state of
a robot nobody has cleared.

### Cadence

The monitor runs on every frame, at the full 50 Hz, because it inspects the frame
in front of it rather than sampling a state. It consults the witness only when a
pour posture is actually present, so a witness outage during the approach is not
a reason to stop a robot that is nowhere near pouring.

### A failed transition holds, and cannot silently continue

Every failure path in `session.step` reaches the same `_hold`: publish a Safe
Hold Target, latch, write a `SafetyEvent`, and record the held frame. Four
distinct causes -- monitor veto, policy starvation, bridge refusal, operator
stop -- one response. There is no retry and no recovery, and `finish` refuses to
seal a held run as `completed`, so the one edit that would turn the pilot's
failure rate into a number nobody can trust is unavailable.

### Partial and corrupted episodes

Frames and events append and are never rewritten; the manifest is replaced
atomically. A crash therefore leaves a *short* episode rather than a corrupt one.
Replay refuses to skip an unreadable line, because a quietly shortened episode
reads as a successful one.

Verified end to end: `tests/operation/test_session.py`, and
`scripts/run_operation.py dryrun --lid-closed --inject-pour-at N` holds at the
injected pour with `hold_monitor_veto` while `--lid-open` runs the full replay.
