"""The integration seam: putting the dead-man inside the vendored 50 Hz loop.

Everything else in this package can be exercised without a robot. This module is
the one place that has to change code we do not own, so it is deliberately
shaped to change as little of it as possible.

``TrackerLoopAdapter``  one call the vendored loop makes instead of four reads
``PATCH_ANCHOR``        the exact vendored lines the patch replaces

Why this cannot live above the loop
-----------------------------------
The guard must run in the process that is balancing the robot, because a
watchdog in the publisher cannot fire when the publisher is what failed. On the
vendored path the failure is concrete rather than theoretical: it reads its
target keys with ``json.loads`` on whatever Redis returned, a missing key
returns ``None``, ``json.loads(None)`` raises, the blanket handler around the
loop catches it, and the path out is a ``close()`` whose implementation is
``exit()``.

So a producer that dies does not stop the robot. It kills the thing keeping the
robot upright, which on a standing biped is a fall.

What the adapter guarantees to the loop
---------------------------------------
- It always returns a body target and two hand targets. There is no ``None``
  return and no exception path, so the loop can never be left with nothing to
  execute and can never exit because of a decode failure.
- A lapsed, expired, out-of-order or unreadable frame resolves to the Safe Hold
  Target: the vendored stand pose for the body, the last commanded aperture for
  the hands.
- It reports whether it is holding, so the loop can print it and an episode can
  record it. A hold that nobody can see is indistinguishable from a policy that
  chose to stand still.

The adapter returns plain lists, in the vendored shapes, so the patched lines are
a substitution rather than a rewrite: everything downstream of them in the
vendored loop is untouched.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

from vegapunk.operation.target import HAND_DIM, WholeBodyTarget
from vegapunk.operation.tracker import (
    LAPSE_NONE,
    RedisTrackerTransport,
    TrackerLoopGuard,
    TrackerState,
)

PATCH_ANCHOR = "keys = [\"action_body_unitree_g1_with_hands\""
"""The first vendored line the patch replaces.

Kept here rather than in the patch script so a future vendored update that moves
this block fails loudly at a named constant instead of silently patching the
wrong lines.
"""


class TrackerLoopAdapter:
    """What the vendored real-robot loop calls once per control period.

    Construction is cheap and does no I/O, so it can be built next to the
    existing Redis client in the vendored controller's ``__init__`` without
    changing its startup behaviour.
    """

    def __init__(
        self,
        redis_client: object,
        *,
        hold_periods: int = 5,
        clock_ns: Optional[Callable[[], int]] = None,
    ) -> None:
        self._transport = RedisTrackerTransport(redis_client)
        self._guard = TrackerLoopGuard(hold_periods=hold_periods)
        self._clock_ns = clock_ns or time.time_ns
        self._holds = 0
        self._ticks = 0
        self._last_lapse = LAPSE_NONE
        self._last_detail = ""
        self._state_sequence = 0

    @property
    def holding(self) -> bool:
        return self._guard.latched

    @property
    def hold_reason(self) -> str:
        return self._guard.latch_reason

    @property
    def hold_ticks(self) -> int:
        return self._holds

    @property
    def tick_count(self) -> int:
        return self._ticks

    @property
    def last_lapse(self) -> str:
        return self._last_lapse

    def clear_hold(self, cleared_by: str) -> None:
        """Re-arm after a hold. Only a named human reaches this."""
        if not cleared_by.strip():
            raise ValueError("a hold is cleared by a named human, not by code")
        self._guard.clear_latch()

    def next_target(self) -> tuple[list[float], list[float], list[float], bool]:
        """Read, judge, and return the frame this tick must execute.

        Returns ``(body, left_hand, right_hand, holding)`` in the vendored
        shapes: 35 body values and six per hand. It never raises.
        """
        self._ticks += 1
        now_ns = self._clock_ns()
        try:
            target: Optional[WholeBodyTarget] = self._transport.read_target(now_ns)
        except Exception:
            # The transport is external and may fail in ways we cannot enumerate.
            # Inside a balance loop, an unreadable target and an unreachable
            # Redis are the same condition and resolve the same way.
            target = None

        verdict = self._guard.evaluate(target, now_ns)
        self._last_lapse = verdict.lapse
        self._last_detail = verdict.detail
        if verdict.holding:
            self._holds += 1
        return (
            list(verdict.target.body),
            list(verdict.target.left_hand),
            list(verdict.target.right_hand),
            verdict.holding,
        )

    def publish_state(
        self,
        body: object,
        left_hand: object,
        right_hand: object,
        *,
        applied_target_sequence: Optional[int] = None,
    ) -> None:
        """Publish feedback with the alignment fields the vendored path omits.

        The vendored loop publishes 34 body values and six per hand with no
        timestamp, no sequence, and no indication of which target produced them.
        Without those an observation can only be paired with an action by
        arrival order, which is a guess that degrades exactly when the system is
        under load -- which is exactly when the pairing matters.
        """
        self._state_sequence += 1
        try:
            state = TrackerState(
                sequence=self._state_sequence,
                state_time_ns=self._clock_ns(),
                body=tuple(float(v) for v in body),  # type: ignore[arg-type]
                left_hand=tuple(float(v) for v in left_hand)[:HAND_DIM],  # type: ignore[arg-type]
                right_hand=tuple(float(v) for v in right_hand)[:HAND_DIM],  # type: ignore[arg-type]
                applied_target_sequence=applied_target_sequence,
            )
        except (TypeError, ValueError):
            # Feedback is not on the safety path. A malformed state frame is
            # worth dropping; it is never worth stopping a balance loop for.
            return
        try:
            self._transport.publish_state(state)
        except Exception:
            return
