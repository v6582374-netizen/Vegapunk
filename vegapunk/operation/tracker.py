"""The tracker seam: the vendored transport, and the dead-man inside its loop.

Two things live here, and they are together because they are the two halves of
one physical fact: the whole-body tracker is what keeps this robot standing, so
it is both the only actuator path and the last component that can be trusted to
stop.

``TrackerTransport``   the seam a real transport fills: commit a frame, read state
``RedisTrackerTransport``  the vendored TWIST2 wire, and the only place Redis exists
``TrackerLoopGuard``   the automatic dead-man, designed to run *inside* the 50 Hz loop
``TrackerState``       the feedback half, with the fields the vendored path lacks

Why the guard is not in the bridge
---------------------------------
A watchdog that lives in the publisher cannot fire when the publisher is what
failed. On this embodiment that is not a theoretical gap: the vendored tracker
reads its target keys with no expiry, no sequence and no acknowledgement, a
missing key decodes to ``None``, the resulting exception is swallowed by a
blanket handler, and the path out is a ``close()`` whose implementation is
``exit()``. So deleting a target does not halt the robot -- it kills the process
that was balancing it.

``TrackerLoopGuard`` is therefore written to be embedded in the vendored real
loop, and it is pure: no Redis, no sockets, no clock of its own. It takes the
frame the loop just read and the loop's own timestamp, and returns the frame the
loop must execute this tick. That makes the dead-man testable here, at speed,
without a robot, while still being the thing that runs closest to the hardware.

Its contract is narrow on purpose: it never raises, because an exception inside
a balance loop is the failure mode it exists to remove.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Callable, Mapping, Optional, Protocol, Sequence

from vegapunk.operation.target import (
    BODY_DIM,
    CONTROL_PERIOD_S,
    HAND_DIM,
    JOINT_DIM,
    WholeBodyTarget,
    safe_hold_target,
)

TARGET_BODY_KEY = "action_body_unitree_g1_with_hands"
TARGET_LEFT_HAND_KEY = "action_hand_left_unitree_g1_with_hands"
TARGET_RIGHT_HAND_KEY = "action_hand_right_unitree_g1_with_hands"
TARGET_ENVELOPE_KEY = "action_envelope_unitree_g1_with_hands"

STATE_BODY_KEY = "state_body_unitree_g1_with_hands"
STATE_LEFT_HAND_KEY = "state_hand_left_unitree_g1_with_hands"
STATE_RIGHT_HAND_KEY = "state_hand_right_unitree_g1_with_hands"
STATE_ENVELOPE_KEY = "state_envelope_unitree_g1_with_hands"

STATE_BODY_DIM = 34
"""The vendored body feedback: angular velocity(3) + roll/pitch(2) + joints(29)."""

DEFAULT_EXPIRY_PERIODS = 3
"""How many control periods a frame stays valid when a producer does not say.

Three, because one is indistinguishable from jitter on a 50 Hz loop and a
producer that misses two consecutive ticks has stopped being a producer.
"""


@dataclass(frozen=True)
class TrackerState:
    """One feedback frame, with the alignment fields the vendored path omits.

    The vendored real loop publishes 34 body values and six measured positions
    per hand, and publishes no timestamp, no sequence, and no indication of
    which target produced the state. Without those three an observation cannot
    be paired with the action that caused it, which is the minimum a learning
    record needs, so they are added here rather than reconstructed later from
    arrival order.
    """

    sequence: int
    state_time_ns: int
    body: tuple[float, ...]
    left_hand: tuple[float, ...]
    right_hand: tuple[float, ...]
    applied_target_sequence: Optional[int] = None

    def __post_init__(self) -> None:
        if len(self.body) != STATE_BODY_DIM:
            raise ValueError(
                f"body feedback must carry {STATE_BODY_DIM} values, got "
                f"{len(self.body)}"
            )
        for label, values in (
            ("left_hand", self.left_hand),
            ("right_hand", self.right_hand),
        ):
            if len(values) != HAND_DIM:
                raise ValueError(
                    f"{label} feedback must carry {HAND_DIM} values, got "
                    f"{len(values)}"
                )
        object.__setattr__(self, "body", tuple(float(v) for v in self.body))
        object.__setattr__(
            self, "left_hand", tuple(float(v) for v in self.left_hand)
        )
        object.__setattr__(
            self, "right_hand", tuple(float(v) for v in self.right_hand)
        )

    @property
    def angular_velocity(self) -> tuple[float, ...]:
        return self.body[0:3]

    @property
    def roll_pitch(self) -> tuple[float, ...]:
        return self.body[3:5]

    @property
    def joints_rad(self) -> tuple[float, ...]:
        return self.body[5 : 5 + JOINT_DIM]

    def as_payload(self) -> Mapping[str, object]:
        return {
            "sequence": self.sequence,
            "state_time_ns": self.state_time_ns,
            "body": list(self.body),
            "left_hand": list(self.left_hand),
            "right_hand": list(self.right_hand),
            "applied_target_sequence": self.applied_target_sequence,
        }


class TrackerTransport(Protocol):
    """Whatever carries a frame to the actuators and state back.

    It is a transport and nothing else: no validation, no ordering, no
    authority. Those belong to the bridge, which is the only caller. A transport
    that also judged frames would give the system two places to change the
    rules and one of them would be forgotten.
    """

    def commit(self, target: WholeBodyTarget) -> None:
        """Publish one complete frame. Partial writes are not permitted."""

    def read_state(self) -> Optional[TrackerState]:
        """Return the newest feedback frame, or ``None`` if none has arrived."""


class RedisTrackerTransport:
    """The vendored TWIST2 wire: four keys, written as one atomic commit.

    This is the only module in the package that knows Redis exists. The
    vendored loop reads three separate keys with no relationship between them,
    which means a naive publisher can be observed mid-update -- new body, old
    hands -- and the tracker will faithfully execute that mixture. The pipeline
    here makes the four writes one round trip so no reader sees a torn frame.

    The envelope key is an addition, not a vendored key. It carries sequence,
    timestamps and expiry so a reader can tell a fresh frame from a resident
    one; the vendored keys have no TTL, so a dead producer otherwise leaves its
    last target in place indefinitely, looking exactly like a live one.
    """

    def __init__(
        self,
        client: object,
        *,
        expiry_periods: int = DEFAULT_EXPIRY_PERIODS,
    ) -> None:
        if expiry_periods < 1:
            raise ValueError("expiry_periods must be at least one period")
        self._client = client
        self._expiry_periods = expiry_periods

    def commit(self, target: WholeBodyTarget) -> None:
        envelope = json.dumps(
            {
                "sequence": target.sequence,
                "source_time_ns": target.source_time_ns,
                "valid_until_ns": target.valid_until_ns,
            }
        )
        pipeline = self._client.pipeline()
        pipeline.set(TARGET_BODY_KEY, json.dumps(list(target.body)))
        pipeline.set(TARGET_LEFT_HAND_KEY, json.dumps(list(target.left_hand)))
        pipeline.set(TARGET_RIGHT_HAND_KEY, json.dumps(list(target.right_hand)))
        pipeline.set(TARGET_ENVELOPE_KEY, envelope)
        pipeline.execute()

    def read_target(self, now_ns: int) -> Optional[WholeBodyTarget]:
        """Read the resident frame back, as the tracker loop sees it.

        Returns ``None`` when any part of the frame is absent or unreadable.
        The loop guard treats that as a lapse rather than an error, which is the
        whole point: the vendored path turns the same condition into an
        exception and then into process exit.
        """
        pipeline = self._client.pipeline()
        for key in (
            TARGET_BODY_KEY,
            TARGET_LEFT_HAND_KEY,
            TARGET_RIGHT_HAND_KEY,
            TARGET_ENVELOPE_KEY,
        ):
            pipeline.get(key)
        raw = pipeline.execute()
        if any(value is None for value in raw):
            return None
        try:
            body = json.loads(raw[0])
            left = json.loads(raw[1])
            right = json.loads(raw[2])
            envelope = json.loads(raw[3])
            return WholeBodyTarget(
                sequence=int(envelope["sequence"]),
                source_time_ns=int(envelope["source_time_ns"]),
                valid_until_ns=int(envelope["valid_until_ns"]),
                body=body,
                left_hand=left[:HAND_DIM],
                right_hand=right[:HAND_DIM],
            )
        except (ValueError, TypeError, KeyError, IndexError):
            return None

    def read_state(self) -> Optional[TrackerState]:
        pipeline = self._client.pipeline()
        for key in (
            STATE_BODY_KEY,
            STATE_LEFT_HAND_KEY,
            STATE_RIGHT_HAND_KEY,
            STATE_ENVELOPE_KEY,
        ):
            pipeline.get(key)
        raw = pipeline.execute()
        if raw[0] is None or raw[1] is None or raw[2] is None:
            return None
        try:
            body = json.loads(raw[0])
            left = json.loads(raw[1])[:HAND_DIM]
            right = json.loads(raw[2])[:HAND_DIM]
        except (ValueError, TypeError, IndexError):
            return None
        sequence = 0
        state_time_ns = time.time_ns()
        applied: Optional[int] = None
        if raw[3] is not None:
            try:
                envelope = json.loads(raw[3])
                sequence = int(envelope.get("sequence", 0))
                state_time_ns = int(envelope.get("state_time_ns", state_time_ns))
                applied_raw = envelope.get("applied_target_sequence")
                applied = None if applied_raw is None else int(applied_raw)
            except (ValueError, TypeError):
                return None
        try:
            return TrackerState(
                sequence=sequence,
                state_time_ns=state_time_ns,
                body=body,
                left_hand=left,
                right_hand=right,
                applied_target_sequence=applied,
            )
        except ValueError:
            return None

    def publish_state(self, state: TrackerState) -> None:
        """Publish feedback with its envelope, from inside the tracker loop."""
        pipeline = self._client.pipeline()
        pipeline.set(STATE_BODY_KEY, json.dumps(list(state.body)))
        pipeline.set(STATE_LEFT_HAND_KEY, json.dumps(list(state.left_hand)))
        pipeline.set(STATE_RIGHT_HAND_KEY, json.dumps(list(state.right_hand)))
        pipeline.set(
            STATE_ENVELOPE_KEY,
            json.dumps(
                {
                    "sequence": state.sequence,
                    "state_time_ns": state.state_time_ns,
                    "applied_target_sequence": state.applied_target_sequence,
                }
            ),
        )
        pipeline.execute()


LAPSE_NONE = "none"
LAPSE_ABSENT = "absent"
LAPSE_EXPIRED = "expired"
LAPSE_REGRESSED = "regressed"


@dataclass(frozen=True)
class GuardVerdict:
    """What the tracker loop must execute this tick, and why.

    ``target`` is never ``None``. A loop that received nothing to execute would
    have to invent something, and every reasonable-looking invention -- reuse
    the last frame, publish nothing, reduce gains -- is a distinct way to drop a
    standing biped.
    """

    target: WholeBodyTarget
    lapse: str
    holding: bool
    detail: str = ""


class TrackerLoopGuard:
    """The automatic dead-man, to be embedded in the vendored 50 Hz loop.

    Given the frame the loop just read, it returns the frame the loop must
    execute. Three conditions resolve to a Safe Hold Target:

    - **absent**: no frame, or a frame that could not be decoded. On the
      vendored path this is the condition that currently ends in process exit.
    - **expired**: a frame older than its own declared validity. A resident
      target in a key with no TTL looks identical to a live one, and a stale
      frame carrying non-zero root velocity keeps the robot walking toward an
      intent that no longer exists.
    - **regressed**: a sequence at or below the last one executed. Redis is
      last-value storage, so a slow producer's late write can otherwise
      resurrect an older intent.

    Holding is latched. Fresh frames do not restore motion authority on their
    own, because an intermittent producer would otherwise oscillate the robot
    between executing and holding, and every oscillation is an unreviewed
    change of motion. The latch is cleared out of band, by the bridge, on a
    named human's word.
    """

    def __init__(self, *, hold_periods: int = 5) -> None:
        self._hold_periods = hold_periods
        self._last_sequence = -1
        self._hold_sequence = 0
        self._left_hand: tuple[float, ...] = tuple()
        self._right_hand: tuple[float, ...] = tuple()
        self._latched = False
        self._latch_reason = ""

    @property
    def latched(self) -> bool:
        return self._latched

    @property
    def latch_reason(self) -> str:
        return self._latch_reason

    def clear_latch(self) -> None:
        """Re-arm. Called only after a named human clears the hold."""
        self._latched = False
        self._latch_reason = ""

    def _hold(self, now_ns: int, lapse: str, detail: str) -> GuardVerdict:
        self._hold_sequence += 1
        if not self._latched:
            self._latched = True
            self._latch_reason = f"{lapse}: {detail}"
        target = safe_hold_target(
            sequence=self._hold_sequence,
            now_ns=now_ns,
            left_hand=self._left_hand or (0.0,) * HAND_DIM,
            right_hand=self._right_hand or (0.0,) * HAND_DIM,
            hold_periods=self._hold_periods,
        )
        return GuardVerdict(
            target=target, lapse=lapse, holding=True, detail=detail
        )

    def evaluate(
        self, target: Optional[WholeBodyTarget], now_ns: int
    ) -> GuardVerdict:
        """Decide this tick. Never raises; never returns ``None``."""
        if self._latched:
            return self._hold(now_ns, LAPSE_NONE, self._latch_reason)
        if target is None:
            return self._hold(
                now_ns, LAPSE_ABSENT, "no readable target frame this tick"
            )
        if target.expired_at(now_ns):
            age_ms = (now_ns - target.valid_until_ns) / 1e6
            return self._hold(
                now_ns,
                LAPSE_EXPIRED,
                f"frame {target.sequence} expired {age_ms:.1f} ms ago",
            )
        if target.sequence <= self._last_sequence:
            return self._hold(
                now_ns,
                LAPSE_REGRESSED,
                f"frame {target.sequence} is not newer than "
                f"{self._last_sequence}",
            )

        self._last_sequence = target.sequence
        self._left_hand = target.left_hand
        self._right_hand = target.right_hand
        return GuardVerdict(target=target, lapse=LAPSE_NONE, holding=False)
