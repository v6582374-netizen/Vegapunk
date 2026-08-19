"""The Target Bridge: the sole path from any producer to the actuators.

Everything that wants to move this robot -- a learned policy, a teleoperator, a
replay -- publishes through here. There is no second path, and that is the
single property the whole harness rests on: if a producer could reach the
transport directly, every guarantee below would be advisory.

The bridge owns policy-layer validity:

- **authority**: a named human's grant, scoped to one configuration
- **ordering**: strictly increasing sequence, so a late frame cannot resurrect
  an old intent
- **freshness**: a frame that arrived after its own expiry is refused rather
  than published
- **atomic commit**: the complete actuation set reaches the transport as one
  write, so no reader observes new body with old hands
- **the latch**: a trip withdraws motion authority until a named human clears it

What the bridge deliberately does not own
----------------------------------------
**The automatic dead-man.** That lives in ``TrackerLoopGuard``, inside the 50 Hz
loop, because a watchdog in the publisher cannot fire when the publisher is what
died. The bridge's hold is the *deliberate* path -- a monitor decided to stop, a
human intervened -- and the guard's hold is the *involuntary* one. Both resolve
to the same Safe Hold Target.

**Torque removal.** The strongest action available here is publishing a frame.
The bridge cannot remove torque and must not pretend to by scaling stiffness
down: reducing gains on a standing biped is a fall, which is a different
accident rather than a safer state. Zero-torque and damping stay with the Manual
Safety Authority -- the remote's damping combination and the physical stop --
which is outside this data plane and outranks everything in it. A bridge that
advertised a guarantee it cannot physically honour would be more dangerous than
one honest about its ceiling.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from vegapunk.operation.target import (
    CONTROL_PERIOD_S,
    HAND_DIM,
    WholeBodyTarget,
    safe_hold_target,
)
from vegapunk.operation.tracker import TrackerState, TrackerTransport

ACCEPTED = "accepted"
REFUSED_NO_AUTHORITY = "refused_no_authority"
REFUSED_STALE = "refused_stale"
REFUSED_OUT_OF_ORDER = "refused_out_of_order"
REFUSED_LATCHED = "refused_latched"
REFUSED_SATURATED = "refused_sustained_saturation"

SUSTAINED_SATURATION_PERIODS = 10
"""How many consecutive clamped frames mean the producer, not the arithmetic.

Ten periods is 200 ms at 50 Hz. The contract saturates an out-of-range root
channel rather than refusing it, because root velocity is a finite difference of
a human demonstrator's motion and isolated frames overshoot any ceiling by
differentiation noise alone -- in the six recorded episodes on this embodiment
the longest run above the speed ceiling is a single 20 ms frame, and 0.076% of
frames clamp at all.

That tolerance is exactly what a runaway producer would exploit. A policy
commanding 5 m/s forever is clamped to the ceiling on every frame and would
otherwise walk the robot into the bench at the maximum speed the bridge allows,
with every individual frame looking acceptable. So the bridge counts the run:
noise cannot hold a ceiling for ten consecutive periods, and a producer that
does is not producing noise.
"""


@dataclass(frozen=True)
class MotionGrant:
    """One named human's authority to command one configuration.

    Deliberately not a flag and not an environment variable: a value someone had
    to construct with their name in it. A missing grant is not a
    misconfiguration to be defaulted -- it is the normal state of a robot nobody
    has cleared.

    It is scoped to a configuration digest because the evidence rule applies to
    the room as much as the software: re-routing the tether, moving the start
    footprint, or moving the witness changes what was authorised.
    """

    authorized_by: str
    statement: str
    granted_at: datetime
    configuration_digest: str

    def __post_init__(self) -> None:
        if not self.authorized_by.strip():
            raise ValueError("a MotionGrant must name who authorized it")
        if not self.statement.strip():
            raise ValueError(
                "a MotionGrant must record what was authorized; an unstated "
                "grant cannot be reviewed"
            )
        if not self.configuration_digest.strip():
            raise ValueError(
                "a MotionGrant must name the configuration it covers"
            )

    def covers(self, configuration_digest: str) -> bool:
        return self.configuration_digest == configuration_digest


@dataclass(frozen=True)
class PublishResult:
    """What the bridge did with one frame, and why.

    ``target`` is the frame that actually reached the transport, which is not
    always the frame that was offered: a hold commits a Safe Hold Target of the
    bridge's own construction. Carrying it here means a caller never has to
    reconstruct what was commanded in order to record it, and therefore cannot
    record something different from what the robot received.
    """

    verdict: str
    sequence: int
    detail: str = ""
    target: Optional[WholeBodyTarget] = None

    @property
    def published(self) -> bool:
        return self.verdict == ACCEPTED


class TargetBridge:
    """The only component permitted to touch a ``TrackerTransport``."""

    def __init__(
        self,
        transport: TrackerTransport,
        configuration_digest: str,
        *,
        grant: Optional[MotionGrant] = None,
        clock_ns: Optional[Callable[[], int]] = None,
        hold_periods: int = 5,
    ) -> None:
        if not configuration_digest.strip():
            raise ValueError("a bridge must know which configuration it serves")
        self._transport = transport
        self._configuration_digest = configuration_digest
        self._grant = grant
        self._clock_ns = clock_ns or time.time_ns
        self._hold_periods = hold_periods
        self._last_sequence = -1
        self._latched = False
        self._latch_reason = ""
        self._last_hands: tuple[tuple[float, ...], tuple[float, ...]] = (
            (0.0,) * HAND_DIM,
            (0.0,) * HAND_DIM,
        )
        self._published = 0
        self._refused = 0
        self._saturated_run = 0
        self._longest_saturated_run = 0

    @property
    def latched(self) -> bool:
        return self._latched

    @property
    def latch_reason(self) -> str:
        return self._latch_reason

    @property
    def published_count(self) -> int:
        return self._published

    @property
    def refused_count(self) -> int:
        return self._refused

    @property
    def saturated_run(self) -> int:
        """Consecutive frames whose root channels arrived clamped."""
        return self._saturated_run

    @property
    def longest_saturated_run(self) -> int:
        """The longest such run this bridge has seen, for the episode record."""
        return self._longest_saturated_run

    @property
    def authorized(self) -> bool:
        return self._grant is not None and self._grant.covers(
            self._configuration_digest
        )

    def grant_authority(self, grant: MotionGrant) -> None:
        """Install a grant. It must name this exact configuration."""
        if not grant.covers(self._configuration_digest):
            raise ValueError(
                "this grant authorises configuration "
                f"{grant.configuration_digest!r}, not "
                f"{self._configuration_digest!r}"
            )
        self._grant = grant

    def withdraw_authority(self) -> None:
        self._grant = None

    def publish(self, target: WholeBodyTarget) -> PublishResult:
        """Validate one frame and, if it passes, commit it atomically."""
        if self._latched:
            self._refused += 1
            return PublishResult(
                REFUSED_LATCHED, target.sequence, self._latch_reason
            )
        if not self.authorized:
            self._refused += 1
            return PublishResult(
                REFUSED_NO_AUTHORITY,
                target.sequence,
                "no named human has granted motion authority for this "
                "configuration",
            )
        if target.sequence <= self._last_sequence:
            self._refused += 1
            return PublishResult(
                REFUSED_OUT_OF_ORDER,
                target.sequence,
                f"sequence {target.sequence} is not newer than "
                f"{self._last_sequence}",
            )
        now_ns = self._clock_ns()
        if target.expired_at(now_ns):
            self._refused += 1
            return PublishResult(
                REFUSED_STALE,
                target.sequence,
                f"frame {target.sequence} expired before it could be "
                "published",
            )

        if target.saturated:
            self._saturated_run += 1
            self._longest_saturated_run = max(
                self._longest_saturated_run, self._saturated_run
            )
            if self._saturated_run >= SUSTAINED_SATURATION_PERIODS:
                detail = (
                    f"{self._saturated_run} consecutive frames arrived clamped "
                    f"({', '.join(target.clamped)}): this is a producer "
                    "commanding beyond the envelope, not differentiation noise"
                )
                held = self.hold(detail)
                self._refused += 1
                return PublishResult(
                    REFUSED_SATURATED,
                    target.sequence,
                    detail,
                    target=held.target,
                )
        else:
            self._saturated_run = 0

        self._transport.commit(target)
        self._last_sequence = target.sequence
        self._last_hands = (target.left_hand, target.right_hand)
        self._published += 1
        return PublishResult(ACCEPTED, target.sequence, target=target)

    def hold(self, reason: str) -> PublishResult:
        """Publish a Safe Hold Target and latch motion authority withdrawn.

        This is the deliberate hold: a monitor refused a gate, an operator
        intervened, an episode ended. It publishes rather than withholds,
        because on this embodiment silence is not safety.

        A hold is always published, even with no grant installed. Refusing to
        stop because nobody authorised stopping would be the one refusal that
        makes things worse.
        """
        if not reason.strip():
            raise ValueError("a hold must record why it was called")
        now_ns = self._clock_ns()
        self._last_sequence += 1
        left, right = self._last_hands
        target = safe_hold_target(
            sequence=self._last_sequence,
            now_ns=now_ns,
            left_hand=left,
            right_hand=right,
            hold_periods=self._hold_periods,
        )
        self._transport.commit(target)
        if not self._latched:
            self._latched = True
            self._latch_reason = reason
        return PublishResult(ACCEPTED, target.sequence, reason, target=target)

    def clear_latch(self, cleared_by: str, statement: str) -> None:
        """Re-arm after a hold. Only a named human may do this.

        Fresh, valid frames never clear a latch on their own: an intermittent
        producer would otherwise oscillate the robot between holding and
        executing, and each oscillation is a motion change nobody reviewed.
        """
        if not cleared_by.strip():
            raise ValueError("a latch is cleared by a named human, not by code")
        if not statement.strip():
            raise ValueError(
                "clearing a latch must record what was checked before "
                "re-arming"
            )
        if not self._latched:
            return
        self._latched = False
        self._latch_reason = ""

    def read_state(self) -> Optional[TrackerState]:
        """Feedback needs no authority. Reading is never the dangerous direction."""
        return self._transport.read_state()
