# Define the verifiable instrument state contract

Type: grilling
Status: resolved
Assignee: codex
Labels: wayfinder:grilling

## Question

What is the authoritative state graph for the first instrument loop, and what
direct evidence authorizes every transition?

Resolve the operation as instrument facts rather than named robot gestures:
the initial safe state, lid-open state, cup-held state, transfer-complete
state, cup-released state, lid-closed terminal state, and every failure/hold
state. For each, choose the observable source, freshness requirement,
confidence/ambiguity rule, reset owner, and the condition that prevents moving
to the next state.

The answer must address the concrete case where a human can see an apparently
successful pour but no system observation can prove it.

## Answer

**The state contract is a monitor, not a sequencer. It gates exactly one
transition, on one bit, from a witness that does not share the policy's eyes.
Liquid transfer is not a state at all — it is an outcome label measured off the
robot after the episode ends.**

Decided from first principles at the user's direction. Three of the ticket's own
premises turned out to be wrong, and saying so is most of the answer.

### The graph must not be the control flow

The named states — lid open, cup held, transfer complete, cup released, lid
closed — describe the task, so the reflex is to make them the sequence the run
executes: reach state, verify, authorise next. That reflex reconstructs the
scripted point-to-point behaviour that already works today, wraps a learned
policy around it, and gains nothing. If a supervisor authorises each step, the
policy is a gesture library with extra latency, and the continuous
walk-and-operate behaviour the pilot exists to teach can never appear.

So the contract observes; it does not advance. The policy flows through the
whole loop unsegmented. The monitor watches, and its only authority is
**hold** — resolved as a Safe Hold Target under an Authority Latch, exactly as
the safety envelope already defines. It is deterministic code. No LLM sits in
this path.

### Gating is negative, because only one act is irreversible

A positive gate must be earned by proof. Asking for proof at every state
spreads a weak perceptual budget across six facts and buys nothing, because
almost every state in this loop is *recoverable*: a wrongly-opened lid closes
again, a badly-grasped cup goes back down, a mistimed button press is pressed
again. Recoverable transitions do not need permission — they need to be
recorded, and to be interruptible.

Exactly one act in the loop is irreversible: **the pour**. Liquid leaves the cup
once. Pouring onto a closed lid is the failure the ticket is really about, and
it is the only one that cannot be undone by continuing.

That collapses the verification problem to a single question — *is the lid
open?* — and it is the most observable fact in the entire scene: binary,
static, large, and changed only by a deliberate button press. All verification
budget concentrates there.

> One irreversible act, one gate, one bit.

### The witness may not share the policy's eyes

A monitor that reads the same sensor through the same learned model as the thing
it monitors is not a monitor. One perceptual failure takes both out at once, and
the hold never fires precisely when it is needed. So the lid bit comes from an
**Independent Witness**, in this order of preference:

1. **The instrument's own report.** If the machine exposes lid state over any
   interface, that is the witness, and nothing needs building. This is checked
   first because it is strictly better than inferring the fact from pixels.
2. **A fixed bench camera with a geometric test.** Camera and instrument both
   static, so lid-open is a known image region being occluded or revealed — a
   deterministic pixel test, auditable, with no training data and no model.

The witness is **not** a policy observation. If the policy could see it, the
policy would learn to key on it, and the monitor would become part of the
behaviour it is supposed to check. The witness pose joins the scoped
configuration alongside cable routing and the start footprint: moving it
invalidates prior episodes as evidence.

This is also not the answer to the approach corridor's visual structure. That
ticket asks what the *policy* may see; this witness is deliberately outside the
policy's world.

### Three values, never two

The bit is `open | closed | indeterminate`. For permitting the pour,
indeterminate resolves as closed — the fail-safe direction. But it is never
*recorded* as closed, because collapsing unknown into a legal answer destroys
the only measurement that says whether the witness is trustworthy at all.

Freshness splits in two, and conflating them is a real error:

- **Value freshness** is cheap here. The lid cannot change without a button
  press, so the bit is a latched physical state, not a fast signal. It must be
  definite when the pour begins and remain definite throughout it.
- **Channel liveness** is not cheap. Loss of the witness stream is a hold, at
  the witness's own frame rate — the same rule already applied to losing visual
  contact during the approach.

### What each state actually rests on

| State | Machine evidence | Strength | Authority |
| --- | --- | --- | --- |
| Safe start | witness bit definite + hands empty + reset record present | strong | run may not begin without all three |
| Lid open | Independent Witness | strong | **the one gate**: required for the pour |
| Cup held | hand finger positions — a grasp closing on an object stops short of empty closure | moderate, and genuinely non-visual | not a gate; unexpected loss is a hold |
| Transfer complete | **none exists** | — | not a state; see below |
| Cup released | commanded aperture open, cup visible at rest | weak | recorded only |
| Lid closed (terminal) | Independent Witness + hands empty | strong | run *completion*, not run success |

Hand occupancy earns its place by being the loop's only evidence channel that
is neither vision nor an added sensor. It cannot say the cup is held *well*, but
it detects the drop, and a drop must stop the robot.

### The pour that nothing can prove

The honest position: **no observation available to this system establishes that
liquid entered the vessel.** Every candidate is a proxy — a wrist view of a
tilted cup, a plausible trajectory, a confident human watching. Admitting any of
them as evidence would put a guess inside a safety contract, and it is the exact
failure mode the ticket names.

So transfer stops being a state and becomes an **outcome label**, produced
outside the loop by physical measurement: the mass difference of the cup and,
where the vessel can be handled, of the receiver too. A bench scale converts an
unobservable state into a number. It is never real-time evidence and it
authorises nothing; it labels the episode after the fact.

Three consequences:

- **Mass out is necessary, not sufficient.** Liquid leaving the cup does not
  prove liquid entering the vessel — the difference is spill. The vessel-side
  measurement closes that gap; where it cannot be taken, the bench witness's
  recording is the only spill account, reviewed by a human and stored as a
  label, still not as proof of success.
- **The operator's impression is recorded, not admitted.** It goes in its own
  field, deliberately separate, so it can be *compared* against the mass. Where
  they disagree, mass wins and the disagreement becomes data about how much the
  operator's eye is worth.
- **Partial transfer is normal, not an error.** Mass delta is continuous, so the
  label has three bands with a genuine middle: an ambiguous episode is excluded
  from the success set and kept in the dataset carrying that label. Nothing is
  discarded and nothing is rounded up.

### The reset is part of the record

There is no autonomous reset. A named human restores lid closed, cup at its
mark, a measured starting volume, vessel emptied, floor dry — and that record,
with the name and the volume, is part of the episode. A pour outcome measured
against an unrecorded starting state is not a measurement.

### What this establishes

**A gate needs proof; flow does not.** Proceeding through a recoverable state
requires no verification, because the remedy for being wrong is to continue
correctly. Only an irreversible act must be earned, and it is earned by an
independent witness or not at all. Where no witness can exist, the fact leaves
the control plane entirely and becomes a measured label — it is never softened
into a confident guess that a safety decision then rests on.

## Answer

**The instrument has two gated states, not six: lid open and lid closed.**
Everything else in the loop — cup held, pouring, cup released — is not an
instrument state, because nothing in this deployment can witness it. The state
contract shrinks to what can actually be witnessed, and the rest of the loop is
the policy's continuous business.

This is not a simplification for convenience. It follows from one rule.

### A state exists only if something can witness it

A state graph whose nodes cannot be observed is not a contract; it is a
narration of the intended motion, and it fails in exactly the way that matters
— it reports progress that did not happen. So each proposed state was tested
against a single question: what physical channel distinguishes it from its
neighbour?

- **Lid open / closed** survives. It is a large, binary, externally visible
  geometric change in a fixed location. One witness can separate it.
- **Cup held** does not. The only candidate evidence is Revo2 finger position
  feedback, and a closed hand on nothing is indistinguishable from a closed
  hand on a cup. Aperture is not possession.
- **Transfer complete** does not. This is the case the ticket demanded be
  addressed, and it is answered below.
- **Cup released** does not, for the mirror of the cup-held reason, and adds
  nothing: an open hand proves neither that the cup left it nor that the cup is
  upright on the bench.

What remains is three ontological categories, and the harness must never let
them blur:

| Category | Established by | Used for |
| --- | --- | --- |
| **Gated Instrument State** | An Independent Witness, in real time | Authorizing motion |
| **Episode Outcome** | Physical measurement, off the robot, after the episode | Training filtering, go/no-go |
| **Unwitnessed Interior** | Nothing | Nothing — it is the policy's continuous behaviour |

### The two gates

Only two transitions in this loop can cause a physically bad event that the
policy's own eyes might authorize incorrectly, so only two are gated:

- **Pour gate**: pouring is authorized only while the witness reports lid
  **open**. This is what prevents liquid on a closed instrument.
- **Close gate**: pressing the close button is authorized only while the
  witness reports lid **open** and the lid aperture **clear**. This is what
  prevents the lid closing on a hand or a cup.

The terminal state is the witness reporting **closed** and continuing to report
closed for a short dwell. Pressing the green button is a robot action, not a
terminal state.

Note what this deletes. Both button presses need no press-force sensing, no
screen reading, and no click detection: the *only* evidence a button press
worked is the lid state change it was supposed to cause. Effects are witnessed;
actions are not.

### The witness must not be the policy's eyes

The gate exists to constrain the policy, so it cannot be computed from the
policy's own observation. A policy that misperceives the lid as open would
otherwise authorize its own pour, and the gate would be decoration. Hence
**Independent Witness**: a channel outside the policy's observation set —
preferably the instrument's own report, otherwise a fixed bench camera running
a geometric test on a known region.

Its pose becomes part of the scoped configuration, like cable routing and start
footprint: moving it invalidates prior episodes as evidence about the new
arrangement.

### The witness produces three values, and one of them is a hold

`open`, `closed`, `indeterminate`. The third is mandatory, because occlusion by
the robot's own arm is a normal event in this loop, not a fault. It is a
first-class value rather than an error, and it resolves as follows:

- **Freshness.** A gate is satisfied only by a witness reading younger than a
  bounded age. A stale reading is `indeterminate`, never the last known value.
- **Ambiguity.** `indeterminate` never satisfies a gate and never blocks one by
  default — it *holds*. Consistent with the safety envelope: the hold is a
  positively published Safe Hold Target, and it latches until a named human
  clears it. There is no automatic retry, no waiting-and-hoping, no
  probability threshold for the policy to interpret.
- **Debounce.** A state transition is accepted only after the new value is held
  for a dwell, so a single frame does not open a gate.

Every failure in this contract collapses to that one state. There is no
per-state failure taxonomy, because the response is identical and a taxonomy
would only invite different responses.

### The pour that a human can see and no system can prove

**Then it is not a state, and it never gates anything.** Promoting an
unwitnessable fact to a gate is the single worst move available here: it forces
either a fabricated observation or a human clicking "yes it poured", and both
teach the harness that assertion is evidence.

Transfer is instead an **Episode Outcome**, established after the episode by
mass: the receiving vessel or the cup is weighed off the robot, against a
recorded starting volume, and labelled in three bands — transferred, partial,
none. Mass is chosen because it is the only channel here that is cheap,
direct, and immune to the occlusion and specularity that defeat vision on a
clear liquid in a white room.

Three consequences, all deliberate:

- The robot never waits for pour confirmation. It proceeds to release the cup
  and close the lid on the gates above. The run's *safety* does not depend on
  knowing whether liquid moved; only the run's *score* does.
- A human's observation of the pour is recorded as **Human Testimony**, stored
  under its own type, never as an observation and never able to satisfy a gate.
  It is retained because it is genuinely useful for failure analysis — it is
  simply not evidence.
- Episodes whose outcome is `none` are still valid records of a behaviour. They
  are excluded from imitation training by label, not deleted, because the
  pilot's job is to find out what the loop actually does.

### Reset

Every episode's reset is performed and recorded by a **named human**: lid
closed, cup at its start pose with a recorded starting volume, receiving vessel
restored, floor and tether restored. No software owns reset, and no reset is
inferred from a prior episode's end state. An outcome measured against an
unrecorded starting state is not a measurement.

### What this leaves open

Two facts the contract now depends on are physical, not architectural, and are
ticketed:

- Whether an Independent Witness channel exists at all, and what it delivers —
  [Establish the Independent Witness for lid state](15-establish-the-independent-witness-for-lid-state.md).
- Whether the pour can be weighed, at what resolution, and at what cost per
  episode, which also fixes the three bands' boundaries —
  [Provision the pour outcome measurement](16-provision-the-pour-outcome-measurement.md).

If the instrument reports its own lid state, the first collapses to nothing and
the fixed camera disappears. That is the outcome to hope for.
