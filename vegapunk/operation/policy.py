"""The serving shape: a slow intent, a fast target, and one clock that matters.

The architectural sample splits its VLA in two: a vision-language model that
reads cameras and an instruction and emits a compact intent, running below 5 Hz,
and a small policy that turns that intent plus live observations into short
whole-body action chunks at 50 Hz. The tracker executes those chunks and keeps
the robot balanced. The split is not a compute optimisation -- it is what lets a
slow reasoner coexist with a control loop that cannot miss a tick.

That structure is adopted here, and reduced to what one instrument loop needs.

``SlowIntent``      the latent, with the age that makes it usable or not
``IntentProducer``  the seam a vision-language model fills, called off-clock
``FastPolicy``      the seam the 50 Hz target producer fills
``ActionChunk``     several consecutive frames, produced as one inference
``PolicyServer``    the composition: keeps the loop fed at 50 Hz, never blocking

What is deliberately not here
-----------------------------
**No language in the loop.** The instruction is fixed for this loop, so the slow
system's job is perception, not interpretation. Nothing in this path lets a
language model choose an action, and the monitor's gate is not reachable from
here at all.

**No reward model, no online updates.** The sample's real-robot RL loop trains
against human-labelled failures. That is a scale problem, not this loop's
problem, and adding it before the first behaviour exists would be building the
correction mechanism for a policy that does not yet run.

**No blocking on the slow system.** The fast policy consumes the newest intent
available and never waits for a fresh one, because a control loop that waits for
a vision-language model is a control loop that misses ticks. A stale intent is a
degraded input; a missed tick is a dropped robot.

Chunk overlap
-------------
A chunk covers several control periods, so a new chunk arrives while the previous
one is still executing. The seam between them is where a naive implementation
produces a visible jerk: two independent inferences disagree about where the arm
was going. ``PolicyServer`` therefore serves the *older* chunk through its
overlap region and only switches once the new chunk has caught up to the current
tick, so the executed sequence is always continuous even when inference is late.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Mapping, Optional, Protocol, Sequence

from vegapunk.operation.target import (
    CONTROL_PERIOD_S,
    WholeBodyTarget,
    safe_hold_target,
)
from vegapunk.operation.tracker import TrackerState

DEFAULT_INTENT_MAX_AGE_S = 1.0
"""How old an intent may be before the fast policy is told it is unusable.

One second. The slow system runs below 5 Hz by design, so several control periods
of age is normal and not a fault; a full second means it has stopped.
"""

DEFAULT_CHUNK_PERIODS = 8
"""Control periods per inference: 160 ms at 50 Hz.

Long enough that inference has time to produce the next chunk, short enough that
the policy re-reads the world several times per second while walking.
"""


@dataclass(frozen=True)
class Observation:
    """What both systems see. Images are references, not pixels.

    This is the policy's view of the world, and it is deliberately a different
    type from the monitor's evidence. The monitor's lid bit is not in here, and
    must never be: a policy that could see the gate's evidence would learn to key
    on it, and the gate would stop constraining the policy it exists to
    constrain.
    """

    time_ns: int
    images: Mapping[str, object]
    state: TrackerState

    def __post_init__(self) -> None:
        if self.time_ns <= 0:
            raise ValueError("an observation must carry a positive timestamp")
        if not self.images:
            raise ValueError("an observation with no image is not an observation")
        object.__setattr__(self, "images", dict(self.images))


@dataclass(frozen=True)
class SlowIntent:
    """The compact representation the slow system hands to the fast one.

    Opaque on purpose. Nothing downstream interprets its contents, which is what
    keeps the slow system replaceable without touching the control path.
    """

    latent: tuple[float, ...]
    produced_at_ns: int
    sequence: int
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.latent:
            raise ValueError("an empty intent is not an intent")
        if self.produced_at_ns <= 0:
            raise ValueError("an intent must carry a positive timestamp")
        object.__setattr__(
            self, "latent", tuple(float(value) for value in self.latent)
        )

    def age_s(self, now_ns: int) -> float:
        return max(0.0, (now_ns - self.produced_at_ns) / 1e9)


class IntentProducer(Protocol):
    """The vision-language half. Called off the control clock.

    Its latency is expected to be tens or hundreds of milliseconds, which is why
    nothing in the fast path calls it synchronously.
    """

    def infer(self, observation: Observation) -> SlowIntent:
        """Read the scene and produce the newest intent."""


@dataclass(frozen=True)
class ActionChunk:
    """Several consecutive target frames produced by one inference.

    ``first_tick`` anchors the chunk on the control clock, so the server can tell
    whether a newly arrived chunk is still relevant or was overtaken by the loop
    while it was being computed.
    """

    first_tick: int
    frames: tuple[WholeBodyTarget, ...]

    def __post_init__(self) -> None:
        if self.first_tick < 0:
            raise ValueError("first_tick must be non-negative")
        if not self.frames:
            raise ValueError("an empty chunk commands nothing")
        object.__setattr__(self, "frames", tuple(self.frames))

    @property
    def last_tick(self) -> int:
        return self.first_tick + len(self.frames) - 1

    def covers(self, tick: int) -> bool:
        return self.first_tick <= tick <= self.last_tick

    def at(self, tick: int) -> WholeBodyTarget:
        if not self.covers(tick):
            raise ValueError(
                f"tick {tick} is outside this chunk "
                f"[{self.first_tick}, {self.last_tick}]"
            )
        return self.frames[tick - self.first_tick]


class FastPolicy(Protocol):
    """The 50 Hz half: intent plus live observation becomes a chunk of targets."""

    def act(
        self,
        observation: Observation,
        intent: Optional[SlowIntent],
        first_tick: int,
    ) -> ActionChunk:
        """Produce the next chunk, starting at ``first_tick``."""


class PolicyServer:
    """Keeps the control loop fed at 50 Hz without ever blocking on inference.

    One tick, one frame, no gaps. Three rules produce that:

    - **Serve from the chunk that covers this tick.** If the current chunk still
      covers it, it is served, even when a newer chunk has arrived: switching
      mid-overlap is what produces a visible jerk at the seam.
    - **Ask for the next chunk before the current one runs out.** Inference
      starts with a lead so a late answer is absorbed by the remaining frames
      rather than by the robot.
    - **Never invent a frame.** If no chunk covers this tick, the server returns a
      Safe Hold Target and says so. It does not repeat the last frame, which on
      a walking robot means continuing to walk toward an intent nobody produced.

    A fourth rule is a consequence of the third: a fast policy that *raises* is
    treated exactly like one that produced nothing. Inference runs arbitrary
    learned code, and an exception escaping into the control thread is the
    failure mode the tracker's dead-man was written to remove; re-introducing it
    one layer up would undo that.
    """

    def __init__(
        self,
        fast: FastPolicy,
        *,
        intent_max_age_s: float = DEFAULT_INTENT_MAX_AGE_S,
        refill_lead: int = 2,
        clock_ns: Optional[Callable[[], int]] = None,
    ) -> None:
        if refill_lead < 1:
            raise ValueError("refill_lead must be at least one tick")
        self._fast = fast
        self._intent_max_age_s = intent_max_age_s
        self._refill_lead = refill_lead
        self._clock_ns = clock_ns or time.time_ns
        self._intent: Optional[SlowIntent] = None
        self._chunk: Optional[ActionChunk] = None
        self._tick = 0
        self._starved = 0
        self._inferences = 0
        self._failures = 0
        self._last_failure = ""

    @property
    def tick(self) -> int:
        return self._tick

    @property
    def starved_ticks(self) -> int:
        return self._starved

    @property
    def inference_count(self) -> int:
        return self._inferences

    @property
    def failure_count(self) -> int:
        """How often the fast policy raised instead of producing a chunk."""
        return self._failures

    @property
    def last_failure(self) -> str:
        return self._last_failure

    def offer_intent(self, intent: SlowIntent) -> None:
        """Install a newer intent. Older ones are ignored, never re-applied."""
        if self._intent is not None and intent.sequence <= self._intent.sequence:
            return
        self._intent = intent

    def usable_intent(self, now_ns: int) -> Optional[SlowIntent]:
        """The intent the fast policy may use, or ``None`` if it has gone stale."""
        if self._intent is None:
            return None
        if self._intent.age_s(now_ns) > self._intent_max_age_s:
            return None
        return self._intent

    def step(self, observation: Observation) -> tuple[WholeBodyTarget, bool]:
        """Produce the frame for this tick. Returns ``(target, starved)``.

        ``starved`` is true when no chunk covered the tick and a Safe Hold Target
        was substituted. It is surfaced rather than logged because a starved tick
        is a fact the episode record must carry: it is the difference between a
        policy that behaved badly and a policy that was never asked.
        """
        tick = self._tick
        self._tick += 1

        needs_chunk = self._chunk is None or not self._chunk.covers(tick)
        running_out = (
            self._chunk is not None
            and self._chunk.covers(tick)
            and self._chunk.last_tick - tick < self._refill_lead
        )

        if needs_chunk or running_out:
            intent = self.usable_intent(observation.time_ns)
            start = tick if needs_chunk else self._chunk.last_tick + 1
            try:
                chunk = self._fast.act(observation, intent, start)
            except Exception as exc:
                # A producer that raises must not take the control loop with it.
                # This is the same rule the tracker's dead-man applies one layer
                # down: the loop always has a frame to execute, and a failed
                # producer resolves to a hold rather than an exception climbing
                # into the thread that is balancing a standing robot.
                self._failures += 1
                self._last_failure = f"{type(exc).__name__}: {exc}"
            else:
                self._inferences += 1
                if needs_chunk:
                    self._chunk = chunk
                else:
                    self._chunk = self._splice(self._chunk, chunk, tick)

        if self._chunk is not None and self._chunk.covers(tick):
            return self._chunk.at(tick), False

        self._starved += 1
        left = right = None
        if self._chunk is not None:
            tail = self._chunk.frames[-1]
            left, right = tail.left_hand, tail.right_hand
        hold = safe_hold_target(
            sequence=tick,
            now_ns=observation.time_ns,
            left_hand=left if left is not None else (0.0,) * 6,
            right_hand=right if right is not None else (0.0,) * 6,
        )
        return hold, True

    @staticmethod
    def _splice(
        current: ActionChunk, incoming: ActionChunk, tick: int
    ) -> ActionChunk:
        """Join a new chunk onto the tail of the one still executing.

        The already-executed frames are dropped and the remaining current frames
        are kept ahead of the new ones, so the executed sequence never jumps
        backwards and never skips a tick.
        """
        kept = [
            current.at(index)
            for index in range(tick, current.last_tick + 1)
            if index < incoming.first_tick
        ]
        if not kept:
            return incoming
        return ActionChunk(first_tick=tick, frames=tuple(kept) + incoming.frames)


class ReplayFastPolicy:
    """A ``FastPolicy`` that replays recorded frames. No weights, no inference.

    This exists so the whole actuation path -- server, monitor, bridge, guard,
    transport -- can be exercised end to end before any policy is trained. It is
    the honest first producer: a recorded teleoperation episode played back
    through exactly the seam a learned policy will occupy later, which means the
    plumbing is proven by the time weights exist.

    It is not a policy. It ignores its observations, and that is the point: any
    behaviour it produces is the recording's, so a passing end-to-end run says
    the path works, never that anything was learned.
    """

    def __init__(
        self,
        frames: Sequence[WholeBodyTarget],
        *,
        chunk_periods: int = DEFAULT_CHUNK_PERIODS,
    ) -> None:
        if not frames:
            raise ValueError("a replay needs at least one frame")
        if chunk_periods < 1:
            raise ValueError("chunk_periods must be at least one")
        self._frames = tuple(frames)
        self._chunk_periods = chunk_periods

    @property
    def frame_count(self) -> int:
        return len(self._frames)

    def act(
        self,
        observation: Observation,
        intent: Optional[SlowIntent],
        first_tick: int,
    ) -> ActionChunk:
        if first_tick >= len(self._frames):
            raise IndexError(
                f"the recording ended at frame {len(self._frames) - 1}; "
                f"tick {first_tick} is past it"
            )
        window = self._frames[first_tick : first_tick + self._chunk_periods]
        base_ns = observation.time_ns
        frames = tuple(
            WholeBodyTarget(
                sequence=first_tick + offset,
                source_time_ns=base_ns + offset * int(CONTROL_PERIOD_S * 1e9),
                valid_until_ns=base_ns
                + (offset + 3) * int(CONTROL_PERIOD_S * 1e9),
                body=frame.body,
                left_hand=frame.left_hand,
                right_hand=frame.right_hand,
            )
            for offset, frame in enumerate(window)
        )
        return ActionChunk(first_tick=first_tick, frames=frames)
