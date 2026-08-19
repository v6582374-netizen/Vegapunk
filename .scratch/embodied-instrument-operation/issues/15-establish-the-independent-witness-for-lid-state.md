# Establish the Independent Witness for lid state

Type: task
Status: open
Labels: wayfinder:task
Blocked by: 03

## Question

Does a channel exist that can report lid open/closed independently of the
policy's cameras, and what does it actually deliver?

The state contract gates the pour on one bit from a witness that does not share
the policy's eyes. This task establishes whether that witness exists before
anything is built around it.

Check in this order:

1. **The instrument's own report.** Whether the machine exposes lid state over
   any interface at all — digital output, serial, network, panel indicator that
   is machine-readable. If it does, this task is finished here and no camera is
   needed.
2. **A fixed bench camera with a geometric test.** If the instrument reports
   nothing, establish the camera pose, the image region that changes with lid
   state, whether the test is separable under the room's actual lighting, and
   the rate at which the bit is produced.

Report the channel identity, the produced values including how
`indeterminate` arises, the observed rate, and how loss of the channel is
detected. The witness pose becomes part of the scoped configuration, so record
it as such.

The witness must not be reachable by the policy as an observation.
