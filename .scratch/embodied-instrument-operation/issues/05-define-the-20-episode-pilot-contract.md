# Define the 20-episode pilot contract

Type: grilling
Status: open
Labels: wayfinder:grilling
Blocked by: 01, 02, 03, 15

## Question

What makes one first-loop teleoperation episode training-grade, and what
controlled variation belongs in the initial 20-episode pilot?

Resolve the episode boundary, human/operator procedure, physical reset,
observation/action synchronization, task and state labels, invalidation rules,
and a minimal deliberate variation plan. The pilot must teach the continuous
reversible core as one unsegmented behaviour, not five scripted poses stitched
together. Its record must be suitable for later replay and failure analysis.

v1 is stationary, so the variation plan's primary axis is cup pose rather than
start footprint. The pilot is the seed batch that lets a first policy exist at
all; it is not the improvement engine, which is the self-turning batch (17).
