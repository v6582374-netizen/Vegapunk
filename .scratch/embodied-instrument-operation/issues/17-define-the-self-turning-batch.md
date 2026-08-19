# Define the self-turning batch

Type: grilling
Status: open
Labels: wayfinder:grilling
Blocked by: 03, 15, 18, 19

## Question

What owns the concept of "the next episode" and "the next batch", and what
exactly must be true for a batch to turn without a human between episodes?

`OperationSession` is single-episode by construction: it seals a record and
ends. Nothing above it exists. This ticket defines that missing owner — the
component that draws a condition from the batch, runs one episode, takes the
witness verdict, resets, and starts the next one.

Resolve:

- the batch boundary: what a batch is, what it carries, when it is sealed
- the per-episode cycle and which existing module owns each step
- the machine-readable verdict: for the reversible core, success is the lid bit
  flipping twice and returning, so no human judges an episode inside a batch
- the stopping rules, including the consecutive-hold brake, and what a stopped
  batch leaves behind
- what the loop owner is forbidden from doing, so it cannot become a sequencer

The first milestone this must satisfy is a batch whose every episode fails: the
policy publishes a stand target and never reaches the instrument. That batch is
a pass if every verdict, reset and record is present. Competence is not the
thing being tested here; the loop is.

A batch seals its **pre-registration** — the predicted outcome — before the
first episode runs, and the batch record keeps prediction and result side by
side. A batch that records only results cannot show that the plan changed on
evidence (22).

A **generation** is a first-class concept above the batch: one frozen bench
configuration — fixture geometry, witness pose, cup identity, lighting rig. A
batch belongs to exactly one generation. Samples never merge across generations;
only conclusions may be compared. Sealing a generation is atomic: its belief map
freezes, its episodes stop counting as current evidence, and nothing is deleted.

Switching generation is an irreversible act — the retired evidence cannot be
recovered — so it takes the same independent authorisation the pour gate takes: a
**named human** approves it and the approval enters the record with who, when,
what changed, and where the prior generation is sealed. The loop may not open a
generation on its own. This is the pour rule applied a second time, not a new
mechanism.

The loop's one output it cannot execute itself is a **work order**: a proposed
change to the physical bench. The loop has no hands. A work order therefore has a
lifecycle that ends in the record — proposed, executed by a named human,
confirmed, new generation opened, and the first batch of that generation must
carry a real anchor. Because execution changes the generation stamp, a human
cannot quietly adjust a fixture and leave the prior samples looking current.

The loop owner is deterministic code. No LLM sits in it.
