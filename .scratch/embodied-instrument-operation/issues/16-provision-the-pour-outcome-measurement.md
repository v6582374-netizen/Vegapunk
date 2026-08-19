# Provision the pour outcome measurement

Type: task
Status: open
Labels: wayfinder:task
Blocked by: 03

## Question

Can the pour be measured physically, and by what procedure?

Transfer is an outcome label, not a state: it is established by mass, off the
robot, after the episode. This task establishes whether that measurement is
actually available and what it costs per episode.

Resolve: what balance is available and its resolution against the intended
pour volume; whether the receiving vessel can be handled and weighed, or
whether only the cup side can be measured; the weighing procedure and where it
sits relative to the reset; and how much wall-clock time it adds per episode,
since that cost multiplies across every episode collected.

Also fix the reset record's fields — the named human, the starting volume, and
confirmation that lid, cup, vessel and floor were restored — because an
outcome measured against an unrecorded starting state is not a measurement.

The three-band success label's boundaries are set here, from the measured
resolution and the intended volume, not chosen in advance.
