# Verify the robot's behaviour when whole-body commanding stops

Type: task
Status: open
Labels: wayfinder:task

## Question

What does the robot actually do when whole-body commanding ceases mid-run, and
what does the manual damping path actually produce?

The safety envelope decided that safe hold must be a positively published
target and that torque removal belongs to the Manual Safety Authority. Both
claims rest on a fact no source in this workspace can settle: whether the
robot's own firmware applies damping when low-level commanding stops arriving.
That fact decides whether an unhandled process death is a catastrophe or
merely a bad outcome, and therefore how much the bridge's latch has to buy.

Resolve by supervised observation on a hoisted or otherwise secured robot, not
by reading code: what happens when commanding stops, what the remote's damping
combination produces from a commanded state, how long any transition takes,
and whether either path is observable to software after the fact.

Record the answer as facts with the conditions they were measured under. No
policy may hold motion authority until this is known.
