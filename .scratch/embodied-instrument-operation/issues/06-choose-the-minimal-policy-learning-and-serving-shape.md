# Choose the minimal policy learning and serving shape

Type: research
Status: resolved
Assignee: codex
Labels: wayfinder:research
Blocked by: 05

## Question

Given the verified target contract and the 20-episode pilot contract, which
smallest learning and serving architecture can learn this one continuous
instrument loop while preserving the tracker as the sole motor executor?

Compare only primary-source-supported candidates that can consume the recorded
head and wrist observations plus robot state and emit the verified target
contract. Resolve the policy's action horizon, conditioning inputs, temporal
rate, training-data conversion, deployment topology, and the first success
criterion. The answer must reject any candidate that requires a new balance
controller, an unverified action representation, or an LLM in the control
loop.

## Answer

**The architectural sample's three-layer split, reduced to what one loop needs:
a slow intent seam that is currently unused, a fast policy emitting action chunks
at 50 Hz, and the vendored tracker as the sole motor executor.** Built and
exercised against the six real episodes.

- **slow / intent** — `policy.IntentProducer` + `SlowIntent`, below 5 Hz. Seam
  only; the serving path already tolerates `None`, so it is unused rather than
  unplanned. The instruction for this loop is fixed, so there is nothing for a
  language model to interpret.
- **fast / action** — `learn.LearnedFastPolicy`, 50 Hz, emitting an
  `ActionChunk` of 8 control periods (160 ms). Long enough that inference has
  time to produce the next chunk, short enough to re-read the world several times
  a second while walking.
- **executor** — the vendored tracker, unchanged.

**Conditioning**: normalized tracker feedback (46 values) plus image features
through one `ImageEncoder` seam, so training-from-disk and serving-from-camera
cannot drift into different preprocessing. That drift is the classic way a policy
that trained well fails on the robot while every test still passes.

**Output**: 47 values per frame — the contract flattened — denormalized,
projected onto the feasible set, then handed to `WholeBodyTarget`, whose
construction is the validation.

### Why not the sample's flow-matching policy

A flow model earns its complexity on multimodal demonstrations. With no
training-grade dataset in existence yet it would be an untested guess wrapped
around an untested dataset. The architecture is the easiest part of this system to
replace — the contract, bridge, monitor and record are not — so it is
deliberately left simplest.

### The defect this found, which is the real result

A regression network's output is a continuous estimate, so it lands slightly
outside joint ranges routinely: in the first end-to-end serve a finger came back
at -0.0607 rad. The contract refused it, correctly — for a hand-authored frame,
out-of-range means a bug. Every tick starved and the session held.

The fix is not to loosen the contract. **A learned producer must project its
output onto the feasible set before publishing, and record how far it had to
move.** `LearnedFastPolicy` reports `projected_frames` and
`worst_projection_rad`; a small excursion is regression error, a sustained large
one means the policy has learned to command something this embodiment cannot do —
which no loss curve would ever say.

### First success criterion

Not a loss number. A checkpoint is `deployable` only when its dataset carried no
provenance gap *and* held-out whole episodes were evaluated. Trained on the six
existing episodes it reports `deployable=False` and names all four gaps. That is
the correct answer today.
