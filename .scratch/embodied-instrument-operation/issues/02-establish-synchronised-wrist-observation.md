# Establish synchronized wrist observation

Type: task
Status: open
Labels: wayfinder:task

## Question

Can the two existing wrist cameras be recorded, retained, and replayed as
synchronized observations alongside the head camera, robot state, and target
contract?

This task is resolved by one short supervised recording and replay check, not
by a paper design. It must report the camera identities, resolution/rate,
timestamps or synchronization method, calibration/frame metadata, visible
latency, and whether all streams survive an episode as one recoverable record.
No policy data may be collected until the answer is known.

## Additional measurement

While the cameras are up, measure the **head camera's usable field against the
instrument** at candidate approach distances (about 1 m, 2 m, 3 m): at each,
whether the lid, the screen, and the three buttons are resolvable, and where
the instrument sits in frame. The head camera is mounted looking down steeply,
so this bounds the approach corridor and is cheaper to measure now than to
rediscover during collection.

