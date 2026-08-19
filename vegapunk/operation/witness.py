"""The Independent Witness: the lid bit, from outside the policy's eyes.

The loop has exactly one irreversible act -- the pour -- and exactly one gate
guarding it: is the lid open. This module supplies that bit.

Why it may not be a policy observation
--------------------------------------
A monitor that reads the same sensor through the same learned model as the thing
it monitors is not a monitor. One perceptual failure takes both out at once, and
the hold then fails to fire precisely when it is needed. Worse, a policy that
can see the gate's evidence will learn to key on it, and the monitor becomes
part of the behaviour it exists to constrain.

So the witness is a separate channel. This instrument is a passive bench: it
has no interface, no indicator and no state to report, so the bit has to be
produced from outside it. Two ways, in this order of preference:

1. ``SwitchWitness`` -- a physical switch fitted to the lid, read through a
   callable that answers open/closed/unknown. A limit switch, a contact sensor,
   a reed switch on the lid's travel: a few dollars of hardware whose output is
   a boolean nobody has to interpret. Preferred because there is no threshold to
   calibrate, no lighting to survive, and no way for a robot arm to occlude it.
2. ``GeometricWitness`` -- a fixed bench camera running a deterministic test on
   a known image region. Camera and instrument are both static, so lid-open is a
   region being revealed or occluded: no training data, no model, auditable by a
   human looking at two numbers. Needs calibration and can be occluded, which is
   why it is second.

The choice is a human's, and either one satisfies the same interface.

Three values, and the third is the important one
------------------------------------------------
``open``, ``closed``, ``indeterminate``. Occlusion by the robot's own arm is a
normal event in this loop, not a fault, so ``indeterminate`` is a first-class
value rather than an error. It never satisfies a gate and never fails one --
it *holds*. A stale reading is ``indeterminate`` too, never the last known
value: the whole point of a freshness bound is that an old fact about a lid is
not a fact about the lid now.

Debounce exists because a single frame must not open a gate. A new value has to
persist for a dwell before the witness reports it, which costs a fraction of a
second and removes an entire class of one-frame misreads.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Optional, Protocol, Sequence

LID_OPEN = "open"
LID_CLOSED = "closed"
LID_INDETERMINATE = "indeterminate"

_LID_VALUES = frozenset({LID_OPEN, LID_CLOSED, LID_INDETERMINATE})

DEFAULT_MAX_AGE_S = 0.5
"""How old a witness reading may be and still satisfy a gate.

Half a second: the lid is a slow, deliberate, static fact, so this is generous
for the physics and still far tighter than the time a pour takes.
"""

DEFAULT_DWELL_S = 0.3
"""How long a new value must persist before the witness reports it."""


@dataclass(frozen=True)
class LidReading:
    """One raw observation from a witness channel.

    ``source`` names the channel, because a reading whose provenance is unknown
    cannot be audited later, and the whole value of this bit is that it is
    auditable.
    """

    value: str
    observed_at_ns: int
    source: str
    detail: str = ""

    def __post_init__(self) -> None:
        if self.value not in _LID_VALUES:
            raise ValueError(
                f"lid value must be one of {sorted(_LID_VALUES)}, got "
                f"{self.value!r}"
            )
        if self.observed_at_ns <= 0:
            raise ValueError("a reading must carry when it was observed")
        if not self.source.strip():
            raise ValueError("a reading must name the channel it came from")

    def age_s(self, now_ns: int) -> float:
        return max(0.0, (now_ns - self.observed_at_ns) / 1e9)


class LidChannel(Protocol):
    """Whatever physically produces a lid reading.

    Kept as a seam so the debounce and freshness rules below can be tested at
    speed with no instrument in the room, and so the choice between the
    instrument's own report and a bench camera changes nothing above this line.
    """

    @property
    def identity(self) -> str:
        """A stable name for this channel, recorded with every episode."""

    def read(self) -> Optional[LidReading]:
        """The newest reading, or ``None`` when the channel produced nothing."""


class SwitchWitness:
    """Any boolean probe of the lid, wrapped as a channel.

    The preferred witness for this instrument. It is a thin adapter on purpose:
    whatever answers "is the lid open" -- a limit switch on the lid's travel, a
    contact or reed sensor, a GPIO pin, a serial line, a stub in a test -- is
    read by the supplied callable, and the only logic here is mapping its answer
    onto the three values and refusing to invent one.

    It is named for a switch rather than for the instrument because this
    instrument reports nothing. It is a passive bench with no interface and no
    indicator, so the bit does not come from the machine; it comes from hardware
    a human fits to the machine. An earlier version of this class was called
    ``InstrumentReportedWitness`` and its docstring told the reader to check the
    instrument's own interface first. There is no such interface, and a name
    that implies one sends every future reader looking for it.

    ``probe`` returning ``None`` means the channel answered nothing, which is
    ``indeterminate`` rather than an exception, because a witness that raises
    inside a supervised loop converts a hold into a crash.
    """

    def __init__(
        self,
        probe: Callable[[], Optional[bool]],
        *,
        identity: str = "lid_switch",
        clock_ns: Optional[Callable[[], int]] = None,
    ) -> None:
        self._probe = probe
        self._identity = identity
        self._clock_ns = clock_ns or time.time_ns

    @property
    def identity(self) -> str:
        return self._identity

    def read(self) -> Optional[LidReading]:
        now_ns = self._clock_ns()
        try:
            answer = self._probe()
        except Exception as exc:  # the interface is external; it may fail
            return LidReading(
                value=LID_INDETERMINATE,
                observed_at_ns=now_ns,
                source=self._identity,
                detail=f"probe failed: {exc}",
            )
        if answer is None:
            return LidReading(
                value=LID_INDETERMINATE,
                observed_at_ns=now_ns,
                source=self._identity,
                detail="the switch answered nothing",
            )
        return LidReading(
            value=LID_OPEN if answer else LID_CLOSED,
            observed_at_ns=now_ns,
            source=self._identity,
            detail="reported by the lid switch",
        )


@dataclass(frozen=True)
class RegionTest:
    """The deterministic test that turns a fixed camera into a lid bit.

    Both camera and instrument are static, so the lid changes one known region
    of one known image. The test is a scalar statistic of that region compared
    against two thresholds with a gap between them, and the gap is the design:
    a reading that lands inside it is ``indeterminate`` rather than being forced
    to the nearer side. Forcing it is how a half-occluded lid becomes a
    confident wrong answer.

    ``witness_pose_digest`` binds the test to the camera placement it was
    calibrated for. Moving the camera invalidates the thresholds, and therefore
    invalidates prior episodes as evidence about the new arrangement.
    """

    row_span: tuple[int, int]
    column_span: tuple[int, int]
    open_at_or_above: float
    closed_at_or_below: float
    witness_pose_digest: str

    def __post_init__(self) -> None:
        for label, span in (
            ("row_span", self.row_span),
            ("column_span", self.column_span),
        ):
            low, high = span
            if low < 0 or high <= low:
                raise ValueError(f"{label} must be an ordered, non-empty span")
        if self.closed_at_or_below >= self.open_at_or_above:
            raise ValueError(
                "the thresholds must leave an indeterminate gap: "
                f"closed_at_or_below ({self.closed_at_or_below}) must be below "
                f"open_at_or_above ({self.open_at_or_above})"
            )
        if not self.witness_pose_digest.strip():
            raise ValueError(
                "a region test must name the camera pose it was calibrated for"
            )

    def statistic(self, frame: Sequence[Sequence[float]]) -> Optional[float]:
        """Mean intensity over the region, or ``None`` if it does not fit."""
        row_low, row_high = self.row_span
        col_low, col_high = self.column_span
        if len(frame) < row_high:
            return None
        total = 0.0
        count = 0
        for row in frame[row_low:row_high]:
            if len(row) < col_high:
                return None
            for value in row[col_low:col_high]:
                total += float(value)
                count += 1
        if count == 0:
            return None
        return total / count

    def classify(self, statistic: Optional[float]) -> tuple[str, str]:
        if statistic is None:
            return LID_INDETERMINATE, "the region did not fit the frame"
        if statistic >= self.open_at_or_above:
            return LID_OPEN, f"region mean {statistic:.1f} at or above open"
        if statistic <= self.closed_at_or_below:
            return LID_CLOSED, f"region mean {statistic:.1f} at or below closed"
        return (
            LID_INDETERMINATE,
            f"region mean {statistic:.1f} is inside the ambiguous band "
            f"({self.closed_at_or_below}, {self.open_at_or_above})",
        )


class GeometricWitness:
    """A fixed bench camera plus a ``RegionTest``, as a lid channel.

    The fallback, used only if the instrument reports nothing. It has no learned
    component, which is what makes it auditable: a human can read the two
    thresholds and the region and say whether the test is right.
    """

    def __init__(
        self,
        grab_frame: Callable[[], Optional[Sequence[Sequence[float]]]],
        test: RegionTest,
        *,
        identity: str = "bench_camera_lid",
        clock_ns: Optional[Callable[[], int]] = None,
    ) -> None:
        self._grab_frame = grab_frame
        self._test = test
        self._identity = identity
        self._clock_ns = clock_ns or time.time_ns

    @property
    def identity(self) -> str:
        return self._identity

    @property
    def witness_pose_digest(self) -> str:
        return self._test.witness_pose_digest

    def read(self) -> Optional[LidReading]:
        now_ns = self._clock_ns()
        try:
            frame = self._grab_frame()
        except Exception as exc:
            return LidReading(
                value=LID_INDETERMINATE,
                observed_at_ns=now_ns,
                source=self._identity,
                detail=f"frame grab failed: {exc}",
            )
        if frame is None:
            return LidReading(
                value=LID_INDETERMINATE,
                observed_at_ns=now_ns,
                source=self._identity,
                detail="no frame was available",
            )
        value, detail = self._test.classify(self._test.statistic(frame))
        return LidReading(
            value=value,
            observed_at_ns=now_ns,
            source=self._identity,
            detail=detail,
        )


@dataclass(frozen=True)
class WitnessVerdict:
    """The debounced, freshness-checked lid fact a gate is allowed to use."""

    value: str
    reading: Optional[LidReading]
    detail: str

    @property
    def determinate(self) -> bool:
        return self.value in (LID_OPEN, LID_CLOSED)

    @property
    def open(self) -> bool:
        return self.value == LID_OPEN

    @property
    def closed(self) -> bool:
        return self.value == LID_CLOSED


class IndependentWitness:
    """Applies freshness and dwell to one channel, and reports the lid fact.

    This is the only object a gate may ask about the lid. It exists separately
    from the channels because freshness and debounce are the same rules whatever
    produces the bit, and because a channel that owned its own timing rules
    would let a future second channel disagree about what "fresh" means.
    """

    def __init__(
        self,
        channel: LidChannel,
        *,
        max_age_s: float = DEFAULT_MAX_AGE_S,
        dwell_s: float = DEFAULT_DWELL_S,
        clock_ns: Optional[Callable[[], int]] = None,
    ) -> None:
        if max_age_s <= 0:
            raise ValueError("max_age_s must be positive")
        if dwell_s < 0:
            raise ValueError("dwell_s cannot be negative")
        self._channel = channel
        self._max_age_s = max_age_s
        self._dwell_s = dwell_s
        self._clock_ns = clock_ns or time.time_ns
        self._settled = LID_INDETERMINATE
        self._pending: Optional[str] = None
        self._pending_since_ns = 0

    @property
    def identity(self) -> str:
        return self._channel.identity

    def observe(self) -> WitnessVerdict:
        """Read the channel and report what a gate may rely on right now."""
        now_ns = self._clock_ns()
        reading = self._channel.read()

        if reading is None:
            self._pending = None
            self._settled = LID_INDETERMINATE
            return WitnessVerdict(
                LID_INDETERMINATE, None, "the witness channel produced nothing"
            )

        age = reading.age_s(now_ns)
        if age > self._max_age_s:
            self._pending = None
            self._settled = LID_INDETERMINATE
            return WitnessVerdict(
                LID_INDETERMINATE,
                reading,
                f"reading is {age:.2f}s old, above the {self._max_age_s}s "
                "freshness bound; a stale lid fact is not a lid fact",
            )

        if reading.value == LID_INDETERMINATE:
            self._pending = None
            self._settled = LID_INDETERMINATE
            return WitnessVerdict(LID_INDETERMINATE, reading, reading.detail)

        if reading.value == self._settled:
            self._pending = None
            return WitnessVerdict(self._settled, reading, reading.detail)

        if self._pending != reading.value:
            self._pending = reading.value
            self._pending_since_ns = reading.observed_at_ns

        held_s = max(0.0, (reading.observed_at_ns - self._pending_since_ns) / 1e9)
        if held_s < self._dwell_s:
            return WitnessVerdict(
                LID_INDETERMINATE,
                reading,
                f"{reading.value} has only held for {held_s:.2f}s of the "
                f"{self._dwell_s}s dwell",
            )

        self._settled = reading.value
        self._pending = None
        return WitnessVerdict(self._settled, reading, reading.detail)
