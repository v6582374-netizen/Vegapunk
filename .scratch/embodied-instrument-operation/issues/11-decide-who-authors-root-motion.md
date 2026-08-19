# Decide who authors root motion

Type: grilling
Status: resolved
Assignee: codex
Labels: wayfinder:grilling
Blocked by: 01

## Question

Who converts "be at the instrument's operating stance" into the continuously
refreshed local root intent the tracker consumes, and by what evidence?

The established contract removed the assumption that this could be delegated:
the tracker accepts only a root-local velocity, height, roll/pitch and yaw
angular velocity, and contains no localization, mapping, waypoint following or
vision-to-goal path. The joystick velocity command computed in the existing
teleoperation producer is never injected into the published target, so no
positional or route-following authority exists anywhere in the retained stack.

Decide whether the learned policy authors root motion directly from
observations — as the architectural sample does — or whether a separate
stance-seeking layer authors it while the policy owns only the manipulation
phase, and if so what observation closes that loop and what happens at the
handover. Resolve how the walk phase is demonstrated and labelled so the
choice is learnable, and what "arrived" means as an observable fact rather
than an elapsed duration.

This decision determines the policy's conditioning inputs and output scope, so
it precedes the learning and serving shape.

## Answer

**The policy authors root motion directly. No stance-seeking layer, no waypoint
follower, no arrival event, no handover.** The walk is part of the behaviour
being learned, exactly as in the architectural sample.

This is not a preference for the sample's design. It follows from what the
retained stack can and cannot observe.

### Why a separate stance layer cannot exist here

The tracker accepts a root-local *velocity intent*, and nothing anywhere in the
retained stack reports where the robot is. A stance-seeking layer would
therefore have to close its loop one of two ways:

- **By dead reckoning** — integrating its own commanded velocity. This is not
  a position measurement. On a walking biped the mapping from commanded root
  velocity to realised displacement depends on foot slip, tracking error and
  the tracker's own balance corrections, so integrated command diverges from
  reality without bound and without any signal that it has done so. A layer
  built on it would report "arrived" while standing somewhere else.
- **By vision** — which means it needs the cameras, a model of the instrument's
  appearance, and a control loop from image to root intent. That is the policy.
  Building it twice creates two components authoring root motion from the same
  observations, and the only new thing it adds is a disagreement between them.

So the vision loop is the only real loop available, and the policy is the thing
that has vision. Root motion goes there.

### Why there is no arrival event

Because there is no handover, "arrived" is not a state anything needs to
detect. Stance is a continuously corrected visual condition, not a checkpoint
the run passes through. This deletes the failure mode a two-layer design would
have introduced — a handover executed at a pose the manipulation phase was
never trained from — rather than requiring it to be engineered around.

The **Instrument State Contract** still gates the task. Those gates are
instrument facts (lid open, cup held, transfer complete); none of them is a
robot-pose fact, and none may be satisfied by robot pose.

### The invariant this establishes

**Dead reckoning is not evidence.** Integrated velocity, commanded
displacement, and elapsed time may never authorise a transition, satisfy a
precondition, or stand in for an observation. Where the robot is, is only ever
established by what it can see. This is the same rule the safety envelope
already applies to stale observations, extended to position.

### What the data must therefore contain

Two consequences fall on collection, not on architecture:

- **Gaze is body-locked.** The neck is a dormant channel, so the head camera
  points where the torso points. A policy that must keep its target observable
  has to approach roughly facing it. The demonstrated approach must satisfy
  this, or the policy loses its only feedback exactly when it is moving.
- **The pilot must actually contain locomotion.** The six existing episodes do
  not, despite being labelled "walk ahead 1 meter": measured against their own
  timestamps, net root displacement is 0.04-0.25 m with a 1.35-2.42 m path
  length over 40-87 s and near-zero net yaw. The operator shifted in place. As
  walk demonstrations they are empty, and a policy trained on them would learn
  that approaching is standing still.

### Bounded by the tether

The retained deployment is cable-connected — workstation at
`192.168.123.222`, robot at `192.168.123.164`, first-party instructions specify
an Ethernet cable. The approach distance is therefore bounded by a physical
tether before it is bounded by anything about learning, and the cable is
present in every episode as an object that can snag or pull. The approach
geometry this permits is a separate decision, now ticketed.
