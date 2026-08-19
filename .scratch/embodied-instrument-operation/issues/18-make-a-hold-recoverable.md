# Make a hold recoverable

Type: grilling
Status: open
Labels: wayfinder:grilling
Blocked by: 07, 10

## Question

How does a run recover from a hold rather than only stopping at one?

A hold currently latches and terminates the episode: `OperationSession` moves to
HELD, the session is not reusable, and clearing the latch needs a named human.
That is correct for a supervised single run and fatal for a self-turning batch —
the first minor contact calls a human, and the batch's period becomes a person's
period.

Resolve:

- which holds are recoverable and which must still latch for a human; the
  automatic dead-man and any envelope trip are not on the recoverable list by
  default
- what recovery consists of physically, and what evidence says recovery
  succeeded rather than that time passed
- whether recovery ends the episode as a labelled failure and starts a fresh
  one, or resumes the same one — and what the record must show either way
- the per-episode and per-batch limits on recovery attempts
- how a recovered episode is marked so it can never be silently counted as a
  clean run

The existing invariant that a session which held cannot be sealed as completed
must survive this change; recovery may not become the edit that launders a
failure into a success.
