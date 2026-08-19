# Define the target-bridge safety envelope

Type: grilling
Status: resolved
Assignee: codex
Labels: wayfinder:grilling
Blocked by: 01

## Question

What must the single target bridge guarantee before a learned policy is
allowed any motion authority, given that the existing tracker path provides
none of it?

The established contract found the whole automatic-safety layer missing:
Redis values have no TTL, targets carry no sequence or expiry, nothing
acknowledges a target, no watchdog notices a stalled producer, and the
existing stop path resolves to process exit rather than a damping or
zero-torque command. A resident last target can therefore keep a robot
commanded after its producer has died.

Resolve what the bridge owns and what it must refuse: target validity
(freshness, sequence order, shape, bounds), the dead-man rule and exactly what
"safe hold" means as a published target rather than a killed process, whether
a controlled return to the default pose is safe without a human, how a stop
becomes observable and acknowledged, and how this composes with the existing
deterministic supervisor and human motion authority.

The answer must also decide what remains the responsibility of an external or
manual safety authority, so the bridge does not claim a guarantee it cannot
enforce.

## Answer

Decided from first principles at the user's direction rather than by putting
the sub-decisions to them. The first principle is a physical fact about this
embodiment, and every other choice falls out of it.

### Silence is not safety

The retained tracker is not an executor bolted onto a stable machine; it *is*
what keeps a standing biped upright. Two consequences follow, and they
invert the intuition that a welded-base arm would give:

- **Stopping publication is not stopping.** A frozen target is tracked
  faithfully, so a stale frame carrying non-zero root velocity keeps the robot
  walking toward an intent that no longer exists.
- **Absence is worse than staleness.** A missing key decodes to `None`, raises,
  is swallowed by the loop's blanket handler, and reaches a `close()` whose
  implementation is `exit()`. Deleting a target does not halt the robot; it
  kills the process that was balancing it.

Therefore safe hold is a **positively published target**, never an omission,
and the bridge may never express "stop" by withholding or deleting anything.

### Safe hold is per-actuator, not one action

The body's safe direction and the hands' safe direction are opposite, so one
global notion of "hold" would be wrong for one of them.

- **Body**: publish the existing stand target — zero root velocity, nominal
  height, level attitude, zero yaw rate, default joint pose. Its safety does
  not depend on knowing whether the robot was walking or bending, which is the
  property that matters, because the 35-value target expresses root *intent*
  and cannot be read to recover that.
- **Hands**: freeze the last commanded aperture. The hands are position servos
  outside the balance problem, and releasing a held vessel is an irreversible
  physical event, whereas holding it is not.

This asymmetry is now vocabulary (`Safe Hold Target`), because a future reader
will otherwise "simplify" it into one uniform fallback.

### The dead-man belongs in the 50 Hz loop

Authority to move must be revocable by whatever is closest to the hardware and
last to die. A watchdog living in the publisher cannot fire when the publisher
is what failed. So responsibility splits:

- The **tracker loop** owns the fallback: on an expired, malformed, or absent
  target it publishes the Safe Hold Target itself, and a decode failure stops
  being a reason to exit.
- The **target bridge** owns policy-layer validity: shape, bounds, monotonic
  sequence, freshness, atomic commit of the whole actuation set, and the latch.

This accepts modifying the vendored TWIST2 real-robot script. That is
unavoidable: every guarantee above it would otherwise rest on a loop whose
failure mode is process exit.

### The bridge must not claim torque removal

The strongest thing the bridge can do is publish a target. It cannot remove
torque, and it must not pretend to by scaling stiffness down — reducing gains
on a standing biped is a fall, which is a different accident rather than a
safer state. Zero-torque and damping remain with the **Manual Safety
Authority** (the remote's damping combination and the physical stop), which is
outside this data plane and outranks it. The specification states this as a
limit, because a bridge that advertises a guarantee it cannot physically honour
is more dangerous than one that is honest about its ceiling.

### A trip latches until a named human clears it

Automatic re-arming on fresh targets would let an intermittent producer
oscillate the robot between holding and executing, and each oscillation is an
unreviewed motion change. Latching also matches the retained trajectory
ledger, which already quarantines a configuration after any abort with no
automatic retry — one recovery semantics for the whole harness, not two.

### What this leaves open

Whether the robot's firmware applies its own damping when whole-body commanding
ceases is not answerable from source, and it decides whether process death is a
catastrophe or merely bad. It is now
[Verify the robot's behaviour when whole-body commanding stops](12-verify-behaviour-when-commanding-stops.md).
