# Define the batch designer

Type: grilling
Status: open
Labels: wayfinder:grilling
Blocked by: 17, 20, 22

## Question

What chooses the conditions in the next batch, and on what evidence?

This is the loop's "task planning and experiment design" stage. It reads what is
known so far — which conditions succeeded, which failed, how well the predictive
node has been scoring — and emits the next batch.

Resolve:

- the condition space for v1: cup pose is the primary axis, and what else is
  varied, measurable and resettable
- the interface: what a designer receives and what it emits, defined so that the
  first implementation can be a written table and a later one can be a planner
  without the loop changing
- the budget split between the imagined bench and the real bench, governed by
  the node's current score
- the constraint check: a proposed condition must pass the same envelope the
  monitor enforces, and a refused condition is recorded as refused rather than
  quietly dropped
- what "improving experimental effectiveness" is measured as, batch over batch:
  success rate at a fixed envelope, and envelope size at a fixed success rate
- the rule that keeps the designer honest when results are sparse

The first version should be a fixed table with one adaptive rule — spend more of
the next batch where the last one failed. That is already a loop that changes
its plan on results, and it is honest about how little it knows.

The designer's action space is the four classes settled in 22 — conditions,
environment shaping, invocation tuning, minimal added data — and it must state
which class each proposal belongs to, because an environment change reshapes the
field and therefore retires prior episodes as evidence, while a condition change
merely moves within it. Every batch is pre-registered before it runs.

The designer emits along two paths, and the split is structural rather than
cosmetic. **Conditions** the loop executes itself. A **work order** — an
environment change — it cannot execute, because it has no hands; a named human
does, and doing so opens a new generation (17).

A work order must carry its **expected gain**: the envelope it predicts the change
will buy. That expectation is the generation-level pre-registration, and it is
what makes "the AI proposed rebuilding the apparatus" a falsifiable hypothesis
rather than a pleasant sentence. Install the recess, run the first batch of the
new generation, and if the envelope did not grow, the work order was wrong in the
open.

Effectiveness is therefore two independent curves, and the second matters more:

- **Within a generation** — success rate rising under condition search and
  invocation tuning, on a field whose shape is fixed. This has a ceiling.
- **Across generations** — the reliable envelope growing through environment
  shaping. This *changes the shape of the field*, which is why it is the stronger
  reading of "improving experimental effectiveness".

The human approval gate on generation switching is what keeps the second curve
honest: the designer cannot farm it by tearing the bench down repeatedly, so every
work order has to stake a falsifiable expectation.

If an LLM is ever used here, it plans between batches only. It is never in the
control loop, and it never judges an episode.
