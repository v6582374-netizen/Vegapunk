# Define the predictive node contract

Type: grilling
Status: open
Labels: wayfinder:grilling
Blocked by: 15, 17

## Question

What is the interface, the scoring rule, and the authority of the predictive
node inside the loop?

The node is an imagined bench: given a starting frame and an action sequence it
produces the future *witness* view, and the same witness code that judges the
real camera reads the generated one. That is what makes a prediction comparable
to reality as one bit against one bit, and it is why the node generates the
witness view rather than the egocentric view.

Resolve:

- the contract: what a caller supplies, what comes back, and how the node states
  its own confidence
- the scoring rule: how each batch scores the previous batch's predictions, and
  where that score is recorded
- the authority rule: how the score governs how much real-bench budget the
  designer may hand to imagination, so that credibility is earned and not
  granted
- the anchor rule: every batch carries at least one real episode, and a batch
  without one is recorded as unanchored and yields no conclusion
- the implementation ladder and what forces each step up it: a table of observed
  outcomes, then a fitted condition/outcome surface, then a learned generative
  bench. The published tabletop WMA family is a candidate for the top rung only,
  and only in simulation mode.

Two prohibitions are absolute. The node never judges an episode — the witness
does. The node never authorises an action on the real bench.

The interface is fixed once; the rung is expected to change.
