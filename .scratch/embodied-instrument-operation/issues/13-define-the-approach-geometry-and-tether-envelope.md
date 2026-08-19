# Define the approach geometry and tether envelope

Type: grilling
Status: resolved
Assignee: codex
Labels: wayfinder:grilling
Blocked by: 11

## Question

Over what physical approach must the first loop be demonstrated and executed,
given a body-locked gaze and a cable-tethered robot?

Root motion is authored by the policy from vision alone, so the approach is
constrained by what stays observable and what the tether allows rather than by
a route. Resolve the start region, the approach distance and heading envelope,
the required facing during motion, the stance the manipulation phase is
demonstrated from, and how the cable is routed and supervised so it can neither
snag nor pull the robot.

The answer sets the physical envelope every pilot episode is collected inside,
so it precedes the pilot contract.

## Answer

**One marked start footprint roughly 2 m from the instrument, inside a shallow
facing cone, with the tether entering from behind the robot and never crossing
the corridor it walks.** The manipulation phase is demonstrated from a stance
*band*, not a stance point.

The envelope is set by two hard limits and one observed fact about the room.

### The two limits

**Visual contact.** Root motion is authored from vision alone, and gaze is
body-locked to the torso. So the corridor is exactly the region from which the
instrument stays inside the head camera's usable field while the robot is
moving. This yields a positive rule rather than a distance number:

> The current phase's visual target must remain in frame continuously. If it
> leaves frame, that is a hold condition — never something to ride out on
> integrated velocity or a remembered heading.

This is the position-domain reading of the invariant the root-motion decision
already established. It also fixes the heading envelope without measuring it:
the robot approaches roughly facing the instrument because that is the only
posture in which its feedback survives the approach.

**The tether.** The deployment is cable-connected, so approach length is
bounded by cable slack before it is bounded by anything about learning. The
routing rule is directional: the cable enters from **behind** the approach
direction — overhead on a boom, or paid out by a human tether handler standing
behind the start footprint. Rear entry buys three things at once: the cable
never lies in the corridor the robot walks, the handler stays out of a
body-locked forward view, and the handler is positioned to see a snag develop
before it can pull.

The recorded episodes violate this: the cable runs across the floor **between**
the robot and the instrument, directly through the region a walking approach
would cross. That routing must change before any pilot episode is collected.

### The distance, and why it is a band

Two-ish metres, because it must contain genuine locomotion — several steps,
real weight transfer — while staying inside both limits above. The exact figure
is the smaller of what visual contact permits and what the tether permits, and
the first of those is measurable rather than arguable: it is the head camera's
usable field against the instrument at candidate distances. That measurement is
folded into the wrist-observation check, which is already handling this camera.

The manipulation stance is likewise a band. There is no arrival event and no
pose gate, so no single stance is privileged; demonstrating from one exact spot
would teach the policy that the spot is part of the task. The band is bounded
by reach, not by a marker.

### What the room contributes

The captured frames show why this envelope is tight rather than generous. The
background is white drapery and the floor is white reflective tile — both
nearly featureless. The instrument and its table are effectively the only
strong visual structure in the scene, which means visual contact is not merely
the preferred feedback, it is the *only* feedback. Whether that is sufficient,
or whether the corridor needs structure added, is now ticketed separately.

The frames also corroborate the root-motion finding independently: the robot
begins the episode already within arm's reach of the instrument, and root
height sits at 0.87-0.90 m throughout, against 0.72-0.85 m in the offline walk
motions. Those episodes are standing records, not approach records.

### Configuration scope

Cable routing, start footprint, and instrument placement are part of the
configuration that evidence is scoped to. Re-routing the tether or moving the
start footprint invalidates prior episodes as evidence about the new
arrangement — the same rule already applied to embodiment and policy digests,
extended to the room.
