"""The composition: the only thing that runs one instrument loop end to end.

Every other module in this package refuses a different way a run can be wrong.
This one wires them into a single ordered path, and it exists because those
seams do not meet on their own: the policy server knows how to produce a frame
but not whether it may be executed, the monitor knows how to veto a frame but
cannot publish anything, the bridge knows how to publish but not what a run is,
and the episode writer knows what a run leaves behind but never causes one.

One tick, in order:

``observe`` -> ``produce`` -> ``monitor`` -> ``publish`` -> ``record``

The order is the design. The frame is judged before it is published, never
after, so a vetoed pour is a frame the robot never received rather than one it
received and was later told about. And every tick writes exactly one frame to
the record, including a held one, because a run that was prevented is
information about the system and is the only evidence of why it stopped.

What a session may and may not do
---------------------------------
It may hold. It may not advance, retry, or recover. A held session is over:
motion authority is latched withdrawn until a named human clears it, and no
software here can clear it. That is deliberately austere -- it means every hold
costs a human's attention -- and it is the correct starting point, because the
alternative is a harness that quietly retries its way through a failure nobody
reviewed. Whether in-run recovery is worth having is a question for after the
pilot has shown how often holds actually happen.

It never removes torque. The strongest thing in this whole path is a published
frame. Zero-torque and damping belong to the Manual Safety Authority -- the
remote's damping combination and the physical stop -- which sits outside this
data plane and outranks all of it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping, Optional

from vegapunk.operation.bridge import (
    ACCEPTED,
    PublishResult,
    TargetBridge,
)
from vegapunk.operation.episode import (
    EpisodeOutcome,
    EpisodeRecord,
    EpisodeWriter,
    Frame,
    SafetyEvent,
    TERMINATION_COMPLETED,
    TERMINATION_FAULT,
    TERMINATION_HELD,
    TERMINATION_OPERATOR_STOP,
)
from vegapunk.operation.monitor import InstrumentMonitor, PASS
from vegapunk.operation.policy import Observation, PolicyServer
from vegapunk.operation.target import WholeBodyTarget

RUNNING = "running"
HELD = "held"
COMPLETED = "completed"

HOLD_MONITOR_VETO = "hold_monitor_veto"
HOLD_STARVED = "hold_policy_starved"
HOLD_REFUSED = "hold_bridge_refused"
HOLD_OPERATOR = "hold_operator"


@dataclass(frozen=True)
class TickResult:
    """What one control period did, and what the record now holds.

    ``target`` is the frame the robot actually received -- the produced frame
    when it passed, the Safe Hold Target when it did not. A caller that wants to
    know what the robot did reads this, not the policy's output, because those
    are different things precisely when it matters.
    """

    tick: int
    state: str
    target: Optional[WholeBodyTarget]
    monitor_decision: str
    lid: str
    holding: bool
    detail: str = ""

    @property
    def running(self) -> bool:
        return self.state == RUNNING


class OperationSession:
    """One supervised run of one instrument loop.

    Constructed per episode, and not reusable: a session that could be restarted
    would let a held run continue under the same record, and the record would
    then describe two different runs as one.
    """

    def __init__(
        self,
        *,
        policy: PolicyServer,
        monitor: InstrumentMonitor,
        bridge: TargetBridge,
        writer: EpisodeWriter,
        clock_ns: Optional[Callable[[], int]] = None,
    ) -> None:
        self._policy = policy
        self._monitor = monitor
        self._bridge = bridge
        self._writer = writer
        self._clock_ns = clock_ns or time.time_ns
        self._state = RUNNING
        self._detail = ""
        self._ticks = 0
        self._held_at: Optional[int] = None

    @property
    def state(self) -> str:
        return self._state

    @property
    def detail(self) -> str:
        return self._detail

    @property
    def tick_count(self) -> int:
        return self._ticks

    @property
    def record(self) -> EpisodeRecord:
        return self._writer.record

    def _now_ns(self) -> int:
        """A positive timestamp, always.

        Every record type in this package rejects a non-positive timestamp, on
        the grounds that a frame with no time cannot be aligned with anything.
        A clock that returns zero would therefore turn a recordable hold into an
        exception at the exact moment the run is already going wrong, so the
        floor is enforced here rather than trusted.
        """
        now = int(self._clock_ns())
        return now if now > 0 else 1

    def _hold(
        self,
        kind: str,
        detail: str,
        *,
        observation: Optional[Observation],
        lid: str,
        monitor_decision: str,
    ) -> TickResult:
        """Stop the run: publish a hold, latch, and record why.

        The bridge's hold needs no grant, because refusing to stop on the
        grounds that nobody authorised stopping would be the one refusal that
        makes things worse.
        """
        now_ns = self._now_ns()
        result = self._bridge.hold(detail)
        self._state = HELD
        self._detail = detail
        self._held_at = self._ticks

        self._writer.note(
            SafetyEvent(time_ns=now_ns, kind=kind, detail=detail)
        )
        if observation is not None and result.target is not None:
            self._record_frame(
                observation=observation,
                target=result.target,
                lid=lid,
                monitor_decision=monitor_decision,
                holding=True,
            )
        return TickResult(
            tick=self._ticks,
            state=HELD,
            target=result.target,
            monitor_decision=monitor_decision,
            lid=lid,
            holding=True,
            detail=detail,
        )

    def _record_frame(
        self,
        *,
        observation: Observation,
        target: WholeBodyTarget,
        lid: str,
        monitor_decision: str,
        holding: bool,
    ) -> None:
        self._writer.append(
            Frame(
                index=self._ticks,
                time_ns=observation.time_ns,
                images={
                    name: str(reference)
                    for name, reference in observation.images.items()
                },
                state=observation.state,
                target=target,
                lid=lid or "unobserved",
                monitor_decision=monitor_decision,
                holding=holding,
            )
        )

    def step(self, observation: Observation) -> TickResult:
        """Run one control period. Never raises on a producer's behalf."""
        if self._state != RUNNING:
            return TickResult(
                tick=self._ticks,
                state=self._state,
                target=None,
                monitor_decision="",
                lid="",
                holding=self._state == HELD,
                detail=self._detail or f"session is {self._state}",
            )

        target, starved = self._policy.step(observation)

        if starved:
            return self._hold(
                HOLD_STARVED,
                "the policy produced no frame for this tick: "
                f"{self._policy.last_failure or 'no chunk covered it'}",
                observation=observation,
                lid=self._monitor.last_lid,
                monitor_decision="",
            )

        verdict = self._monitor.evaluate(target)
        if verdict.holds:
            return self._hold(
                HOLD_MONITOR_VETO,
                verdict.detail,
                observation=observation,
                lid=verdict.lid,
                monitor_decision=verdict.decision,
            )

        published = self._bridge.publish(target)
        if not published.published:
            return self._hold(
                HOLD_REFUSED,
                f"the bridge refused frame {published.sequence}: "
                f"{published.verdict}: {published.detail}",
                observation=observation,
                lid=verdict.lid,
                monitor_decision=verdict.decision,
            )

        self._record_frame(
            observation=observation,
            target=target,
            lid=verdict.lid,
            monitor_decision=verdict.decision,
            holding=False,
        )
        self._ticks += 1
        return TickResult(
            tick=self._ticks - 1,
            state=RUNNING,
            target=target,
            monitor_decision=verdict.decision,
            lid=verdict.lid,
            holding=False,
        )

    def operator_stop(self, reason: str) -> TickResult:
        """The operator's in-band stop. Not a substitute for the physical one.

        This is the software path, and it is honest about being the weaker one:
        it publishes a hold and latches. The Manual Safety Authority removes
        torque and is what a person reaches for when the robot is doing
        something wrong right now.
        """
        if not reason.strip():
            raise ValueError("an operator stop must record why it was called")
        if self._state != RUNNING:
            return TickResult(
                tick=self._ticks,
                state=self._state,
                target=None,
                monitor_decision="",
                lid="",
                holding=self._state == HELD,
                detail=self._detail,
            )
        return self._hold(
            HOLD_OPERATOR,
            f"operator stop: {reason}",
            observation=None,
            lid=self._monitor.last_lid,
            monitor_decision="",
        )

    def finish(self, outcome: EpisodeOutcome) -> EpisodeRecord:
        """Seal the record with the measured outcome.

        The outcome's ``termination`` must agree with what the session actually
        did. A run that held cannot be sealed as completed: that single edit is
        all it would take to turn the pilot's failure rate into a number nobody
        can trust, and it is exactly the edit a tired operator makes at the end
        of a long session.
        """
        if self._state == HELD and outcome.termination == TERMINATION_COMPLETED:
            raise ValueError(
                "this session held at tick "
                f"{self._held_at}; it cannot be recorded as completed. Use "
                f"{TERMINATION_HELD!r}, {TERMINATION_OPERATOR_STOP!r} or "
                f"{TERMINATION_FAULT!r}"
            )
        if self._state == RUNNING and outcome.termination == TERMINATION_HELD:
            raise ValueError(
                "this session never held; recording it as held would "
                "misreport what happened"
            )
        record = self._writer.complete(outcome)
        self._state = COMPLETED
        return record
