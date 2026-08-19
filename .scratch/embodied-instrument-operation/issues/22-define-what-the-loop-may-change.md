# Define what the loop may change

Type: grilling
Status: resolved
Assignee: codex
Labels: wayfinder:grilling

## Question

If we cannot improve the policy model itself, what does the automated loop
actually change, and why is that worth anything?

Answer from first principles or the loop is theatre: a scripted demonstration
dressed as an experiment, with a rising curve nobody should believe.

## Answer

**Competence is not a number, it is a field. The model is frozen; our position
in its field is not. The loop's action space is everything except the weights.**

### The correction the question needs

"We cannot change the model's ability" is half true. We cannot build a better
foundation than the published VLAs. But every reported success rate — 78% on
this task, 60% on that one — is *one point measured on one carefully arranged
bench*. The same frozen checkpoint may score 0% with the cup at A and 90% with
the cup at B.

So the quantity under study is not the model. It is the map of where the model
works, and our freedom to stand somewhere good on that map.

### The four things the loop may change

1. **Conditions** — cup pose, lighting, initial arm posture, object appearance.
   These are the axes of the field. Searching them changes nothing physical.
2. **Environment** — a locating recess so the cup can only sit one way, a
   high-contrast marker on a button, a cup that is easier to grasp. This does
   not move within the field, it *reshapes the field*. Industrial automation has
   always known this: production lines are made reliable by fixtures, not by
   smarter machines. Embodied AI skipped the lesson because everyone is
   competing on models.
3. **Invocation** — instruction wording for a language-conditioned policy, chunk
   length, replan period, the retreat pose a retry starts from, how many retries
   before giving up. None of this is in the weights, all of it moves the success
   rate, and today it is universally tuned by feel.
4. **Minimal added data** — the smallest version of "changing the model", and
   the only honest one, because the loop says *which* conditions are starved
   instead of scaling a dataset blindly.

Three of the four never touch the model at all. That is why the loop's value
does not depend on our being able to train one.

### The falsifiable claim

> A frozen policy can be taken from ~20% to ~80% on a fixed task by condition
> search, environment shaping, and invocation tuning alone.

Nobody has measured this systematically, and it is the only question that
matters when a laboratory actually tries to deploy a robot. True or false, the
loop answers it with evidence. That is the research goal.

### The four deliverables

- **A reliability envelope with provenance** — not "85%" but "85% with the cup
  inside this 4 cm window, this lighting, this start posture, n=40, adjudicated
  by the independent witness". No paper publishes this; they publish the scalar.
- **Fixture and protocol design** — when the envelope is too small, shape the
  bench. The loop says where the recess goes and how tight it must be.
- **Retry and retreat policy** — grown from recorded failures rather than
  guessed.
- **A minimal data shopping list** — which conditions, how many episodes.

The test of honesty: a laboratory deploying this robot would have to obtain all
four by hand, through undocumented trial and error. The loop does it
systematically, without self-deception, and leaves the evidence. Those are the
four things humans do worst.

### Why the cerebellum is the wrong home for this loop

Locomotion does have a feedback loop — automatic domain randomisation is exactly
"widen the difficulty when the score improves". But that loop lives entirely
inside simulation: its judge is simulator ground truth and its reset is free. It
is a **training loop**, and its object is model parameters.

What the brief asks for is an **experiment loop**, whose object is conditions,
fixtures and protocols in the real world, and whose judge is an instrument.
Manipulation is where that loop has somewhere to stand. This distinction is also
why earlier rounds of this discussion kept sliding: three different loops —
control (20 ms), training (offline), experiment (batch) — were being called one
name.

### What makes it fake — three lines that may not be crossed

- **No real adjudicator.** The verdict comes from the bench witness. The moment
  a human may say "call that one a success", the whole curve is worthless.
- **No real unknown.** If the answer is known and merely re-enacted, this is a
  script. Enforced by **pre-registration**: the batch's predicted outcome is
  written into the record *before* the batch runs, so "the AI changed its plan
  based on results" is auditable history rather than after-the-fact narration.
- **No real cost asymmetry.** A designer with nothing to trade is decoration.
  Here the asymmetry is physical and unavoidable: imagination is cheap, the real
  bench is expensive, the pour is expensive *and* irreversible.

### Where this puts the predictive node

It is the cheap field probe. The field is continuous and high-dimensional and
every real point costs a robot; the node sketches its shape so the real bench
only has to confirm the few points that matter — boundaries, and wherever the
node is least sure.

SimFoundry has already measured the authority this earns: ranking correlation
0.928 against real hardware, while absolute values differ by up to 3× (60% real
versus 20% simulated on one task). So the rule is exact — **it may say "here is
better than there"; it may never say "here is this good"** — and its own score
is tracked every batch.

### One line

We do not change what the model can do. We turn "how much can it do" from an
unfalsifiable legend into a measured map with provenance, then reshape the bench
so the robot stands where it succeeds.

The model is someone else's contribution. The map and the reshaping are ours,
and they are software's native work: exhaustive search, no failure discarded, no
self-deception, evidence retained.
