"""What one run leaves behind, and what it is allowed to prove.

The vendored recorder writes one JSON item per 30 Hz sample carrying an image,
body state, hand state and the target that produced them. That is an
observation/action trace. It is not yet a training or evaluation record, and the
gap is not incidental: it has no camera calibration, no target sequence, no
applied-target alignment, no safety event, no instrument state, no outcome, and
a static goal string that describes picking up a red cup.

This module owns the record that closes that gap.

``Frame``           one synchronized sample: observations, target, witness, state
``EpisodeOutcome``  what the run achieved, measured off the robot after it ended
``HumanTestimony``  what a person saw, stored where it can never gate anything
``ResetRecord``     the physical starting state, signed by a named human
``EpisodeRecord``   the whole run, and the rules for what it may be used for
``EpisodeWriter``   append-only durable capture, one directory per episode

The separation that matters
---------------------------
An **outcome** is measured; a **testimony** is asserted. Both are kept, and they
are different types with different powers, because the moment they share a field
the harness has learned that assertion is evidence. A human who watched a
successful pour that no instrument recorded has produced testimony. The pour is
labelled by mass or not at all.

Why transfer is not a frame field
---------------------------------
Liquid transfer cannot be observed during the run by anything in this room, so
it is not a state and never gates an action. It is established afterwards, by
weighing, against a recorded starting volume. The robot therefore never waits for
pour confirmation: it releases the cup and closes the lid on the monitor's gate
alone. The run's *safety* does not depend on knowing whether liquid moved; only
its *score* does.

Why a failed episode is still a record
--------------------------------------
An episode whose outcome is ``none`` is a valid record of a behaviour and is
excluded from imitation training by *label*, not by deletion. The pilot exists to
find out what the loop actually does, and a dataset that quietly drops its
failures cannot answer that.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

from vegapunk.operation.target import WholeBodyTarget
from vegapunk.operation.tracker import TrackerState

TRANSFER_FULL = "transferred"
TRANSFER_PARTIAL = "partial"
TRANSFER_NONE = "none"

_TRANSFER_BANDS = frozenset({TRANSFER_FULL, TRANSFER_PARTIAL, TRANSFER_NONE})

JUDGED_BY_EYE = "eye"
JUDGED_BY_MASS = "mass"
JUDGED_BY_REVIEW = "video_review"

_JUDGEMENT_METHODS = frozenset(
    {JUDGED_BY_EYE, JUDGED_BY_MASS, JUDGED_BY_REVIEW}
)
"""How an outcome band was arrived at.

Recorded rather than assumed. ``eye`` is the default because it is what will
actually happen at the bench; ``mass`` exists for anyone who wants a number and
carries the stricter rules that come with claiming one; ``video_review`` covers
a label assigned later from the recording, which is how a disputed episode gets
re-judged without re-running it.
"""

TERMINATION_COMPLETED = "completed"
TERMINATION_HELD = "held"
TERMINATION_OPERATOR_STOP = "operator_stop"
TERMINATION_FAULT = "fault"

_TERMINATIONS = frozenset(
    {
        TERMINATION_COMPLETED,
        TERMINATION_HELD,
        TERMINATION_OPERATOR_STOP,
        TERMINATION_FAULT,
    }
)

FRAMES_FILE = "frames.jsonl"
EVENTS_FILE = "events.jsonl"
MANIFEST_FILE = "manifest.json"


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class CameraCalibration:
    """What is needed to interpret one camera's images later.

    Absent from the vendored recorder, and unrecoverable afterwards: an image
    whose intrinsics and mounting frame are unknown cannot be used to train a
    policy that will run on a differently-calibrated camera, and nobody can tell
    from the pixels that this happened.
    """

    identity: str
    width: int
    height: int
    fps: float
    mounted_on: str
    intrinsics: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if not self.identity.strip():
            raise ValueError("a camera must have a stable identity")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("camera resolution must be positive")
        if self.fps <= 0:
            raise ValueError("camera fps must be positive")
        if not self.mounted_on.strip():
            raise ValueError(
                "a camera must record what it is mounted on; a head and a "
                "wrist view are not interchangeable"
            )
        object.__setattr__(
            self, "intrinsics", tuple(float(v) for v in self.intrinsics)
        )

    def as_payload(self) -> Mapping[str, object]:
        return {
            "identity": self.identity,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "mounted_on": self.mounted_on,
            "intrinsics": list(self.intrinsics),
        }


@dataclass(frozen=True)
class Frame:
    """One synchronized sample of everything that mattered at one instant.

    ``images`` maps a camera identity to wherever the image was stored, rather
    than carrying pixels: a record that inlined three camera streams would be
    unreadable and unstreamable, and the point of this type is alignment, not
    storage.

    ``applied_target_sequence`` is the field the vendored path lacks entirely.
    Without it, an observation is paired with an action by arrival order, which
    is a guess that silently degrades exactly when the system is under load.
    """

    index: int
    time_ns: int
    images: Mapping[str, str]
    state: TrackerState
    target: WholeBodyTarget
    lid: str
    monitor_decision: str
    holding: bool = False

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("frame index must be non-negative")
        if self.time_ns <= 0:
            raise ValueError("a frame must carry a positive timestamp")
        if not self.images:
            raise ValueError(
                "a frame with no image is not an observation; drop the frame "
                "rather than recording a blind one"
            )
        if not self.lid.strip():
            raise ValueError(
                "every frame records the witness value, including "
                "'indeterminate'; a blank lid field is indistinguishable from "
                "a witness that was never consulted"
            )
        object.__setattr__(self, "images", MappingProxyType(dict(self.images)))

    def as_payload(self) -> Mapping[str, object]:
        return {
            "index": self.index,
            "time_ns": self.time_ns,
            "images": dict(self.images),
            "state": dict(self.state.as_payload()),
            "target": dict(self.target.as_payload()),
            "lid": self.lid,
            "monitor_decision": self.monitor_decision,
            "holding": self.holding,
        }


@dataclass(frozen=True)
class ResetRecord:
    """The physical starting state one episode was collected against.

    No software owns reset, and no starting state is inferred from a previous
    episode's end: a run whose starting state is unknown cannot be compared with
    any other run.

    What that requires is *sameness*, not precision. The reset asks whether the
    lid was closed, the vessel was in place, and the cup was filled the way it
    always is -- facts a person restoring a bench already knows. A starting
    volume in millilitres is available for anyone who wants it and demanded of
    nobody, because measuring the pour to a millilitre answers a question this
    loop never asks.
    """

    performed_by: str
    performed_at: datetime
    lid_closed: bool
    vessel_restored: bool
    floor_and_tether_restored: bool
    cup_filled: bool = True
    cup_volume_ml: float | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.performed_by.strip():
            raise ValueError("a reset is performed by a named human")
        if self.cup_volume_ml is not None and self.cup_volume_ml < 0:
            raise ValueError("starting volume cannot be negative")

    @property
    def complete(self) -> bool:
        """Whether the bench was actually restored to its starting state.

        ``cup_filled`` counts: an episode that began with an empty cup cannot
        produce a pour, so its outcome says nothing about the behaviour.
        """
        return (
            self.lid_closed
            and self.vessel_restored
            and self.floor_and_tether_restored
            and self.cup_filled
        )

    def as_payload(self) -> Mapping[str, object]:
        return {
            "performed_by": self.performed_by,
            "performed_at": self.performed_at.isoformat(),
            "cup_filled": self.cup_filled,
            "cup_volume_ml": self.cup_volume_ml,
            "lid_closed": self.lid_closed,
            "vessel_restored": self.vessel_restored,
            "floor_and_tether_restored": self.floor_and_tether_restored,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class EpisodeOutcome:
    """What the run achieved, judged by a named human after it ended.

    A person looks into the receiving vessel and picks one of three bands. That
    is not the same concession as letting a human open the pour gate, and the
    difference is the entire reason this type is separate from the witness:

    - The **gate** authorises an irreversible act while the robot is moving. It
      needs a channel the policy cannot see and a person cannot rush, so
      somebody's word may never satisfy it.
    - The **outcome** scores a run that is already over. It authorises nothing
      and nothing physical waits on it, so the cheapest adequate instrument is
      a person looking into the vessel.

    An earlier version of this type demanded a mass and a balance resolution on
    every episode. That was misapplied rigour. It imported a laboratory
    measurement into a behaviour label, made owning a balance a precondition for
    collecting robot data, and quantified millilitres when the only question
    ever asked of the label is which of three bands the pour landed in. Mass
    remains available to anyone who wants it and is required of nobody.

    What survives from that version is the part that was actually load-bearing:
    a label names its judge and its method, so a disagreement later is a
    conversation with a person rather than an argument with a number.
    """

    transfer: str
    judged_by: str
    judged_at: datetime
    lid_closed_at_end: bool
    termination: str
    method: str = JUDGED_BY_EYE
    delivered_mass_g: float | None = None
    balance_resolution_g: float | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        if self.transfer not in _TRANSFER_BANDS:
            raise ValueError(
                f"transfer must be one of {sorted(_TRANSFER_BANDS)}, got "
                f"{self.transfer!r}"
            )
        if self.termination not in _TERMINATIONS:
            raise ValueError(
                f"termination must be one of {sorted(_TERMINATIONS)}, got "
                f"{self.termination!r}"
            )
        if not self.judged_by.strip():
            raise ValueError("an outcome names the human who judged it")
        if not self.method.strip():
            raise ValueError(
                "an outcome records how it was judged; an unstated method "
                "cannot be reviewed or repeated"
            )
        if self.delivered_mass_g is not None and self.delivered_mass_g < 0:
            raise ValueError("delivered mass cannot be negative")
        if self.method == JUDGED_BY_MASS:
            # Only a label that *claims* to be a measurement has to behave like
            # one. This is the one place the old rule was right: a mass with no
            # stated resolution is a number, not a measurement.
            if self.delivered_mass_g is None:
                raise ValueError(
                    f"method {JUDGED_BY_MASS!r} must record delivered_mass_g"
                )
            if (
                self.balance_resolution_g is None
                or self.balance_resolution_g <= 0
            ):
                raise ValueError(
                    f"method {JUDGED_BY_MASS!r} must record a positive "
                    "balance_resolution_g; a mass without a resolution is not "
                    "a measurement"
                )

    @property
    def weighed(self) -> bool:
        return self.delivered_mass_g is not None

    @property
    def within_resolution(self) -> bool | None:
        """Whether a weighed pour exceeded the balance's own noise.

        ``None`` when nobody weighed it, because "not measured" and "measured
        as too small to trust" are different facts and a boolean cannot hold
        both.
        """
        if self.delivered_mass_g is None or self.balance_resolution_g is None:
            return None
        return self.delivered_mass_g >= self.balance_resolution_g

    def as_payload(self) -> Mapping[str, object]:
        return {
            "transfer": self.transfer,
            "judged_by": self.judged_by,
            "judged_at": self.judged_at.isoformat(),
            "method": self.method,
            "delivered_mass_g": self.delivered_mass_g,
            "balance_resolution_g": self.balance_resolution_g,
            "lid_closed_at_end": self.lid_closed_at_end,
            "termination": self.termination,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class HumanTestimony:
    """What a person says they saw. Never an observation, never a gate.

    Retained because it is genuinely useful for failure analysis -- a human is
    the only thing in the room that noticed the cup was already chipped -- and
    kept in its own type precisely so it cannot be mistaken for evidence.
    """

    witnessed_by: str
    recorded_at: datetime
    account: str

    def __post_init__(self) -> None:
        if not self.witnessed_by.strip():
            raise ValueError("testimony names who gave it")
        if not self.account.strip():
            raise ValueError("empty testimony is not worth storing")

    def as_payload(self) -> Mapping[str, object]:
        return {
            "witnessed_by": self.witnessed_by,
            "recorded_at": self.recorded_at.isoformat(),
            "account": self.account,
        }


@dataclass(frozen=True)
class SafetyEvent:
    """One hold, latch, refusal or intervention, in the record forever.

    Absent from the vendored recorder, which is why the six existing episodes
    cannot answer whether anything went wrong during them.
    """

    time_ns: int
    kind: str
    detail: str
    cleared_by: str = ""

    def as_payload(self) -> Mapping[str, object]:
        return {
            "time_ns": self.time_ns,
            "kind": self.kind,
            "detail": self.detail,
            "cleared_by": self.cleared_by,
        }


@dataclass(frozen=True)
class EpisodeRecord:
    """One run, and the rules for what it is allowed to be used for."""

    episode_id: str
    configuration_digest: str
    started_at: datetime
    cameras: tuple[CameraCalibration, ...]
    witness_identity: str
    reset: ResetRecord
    frame_count: int = 0
    outcome: EpisodeOutcome | None = None
    safety_events: tuple[SafetyEvent, ...] = ()
    testimony: tuple[HumanTestimony, ...] = ()
    operator: str = ""

    def __post_init__(self) -> None:
        if not self.episode_id.strip():
            raise ValueError("an episode must be identifiable")
        if not self.configuration_digest.strip():
            raise ValueError(
                "an episode must name the configuration it was collected "
                "against; evidence is scoped to the room as well as the code"
            )
        if not self.cameras:
            raise ValueError("an episode with no camera is not an observation")
        if not self.witness_identity.strip():
            raise ValueError(
                "an episode must name the witness channel that gated it"
            )
        object.__setattr__(self, "cameras", tuple(self.cameras))
        object.__setattr__(self, "safety_events", tuple(self.safety_events))
        object.__setattr__(self, "testimony", tuple(self.testimony))

    @property
    def held(self) -> bool:
        return any(event.kind.startswith("hold") for event in self.safety_events)

    def trainable(self) -> tuple[bool, str]:
        """Whether this episode may be used as imitation data, and why not.

        Four refusals. Each of them corresponds to a way the six existing
        episodes are not training data.
        """
        if self.outcome is None:
            return False, "no outcome: nobody judged whether the pour happened"
        if not self.reset.complete:
            return (
                False,
                "the reset was incomplete, so the starting state is unknown",
            )
        if self.frame_count == 0:
            return False, "no frames were recorded"
        if self.outcome.transfer == TRANSFER_NONE:
            return (
                False,
                (
                    "outcome is 'none': kept as a record of the behaviour, "
                    "excluded from imitation by label rather than deleted"
                ),
            )
        return True, ""

    def as_payload(self) -> Mapping[str, object]:
        return {
            "episode_id": self.episode_id,
            "configuration_digest": self.configuration_digest,
            "started_at": self.started_at.isoformat(),
            "operator": self.operator,
            "cameras": [camera.as_payload() for camera in self.cameras],
            "witness_identity": self.witness_identity,
            "reset": dict(self.reset.as_payload()),
            "frame_count": self.frame_count,
            "outcome": None if self.outcome is None else dict(self.outcome.as_payload()),
            "safety_events": [event.as_payload() for event in self.safety_events],
            "testimony": [entry.as_payload() for entry in self.testimony],
        }


def _append(path: Path, payload: Mapping[str, object]) -> None:
    line = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _write_atomic(path: Path, payload: Mapping[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    text = json.dumps(payload, indent=2, sort_keys=True)
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(text + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


class EpisodeWriter:
    """Append-only capture of one episode into one directory.

    Frames and events are appended and never rewritten; the manifest is replaced
    atomically so a reader never observes half of one. A crash therefore leaves a
    short episode rather than a corrupt one, which is the correct failure mode:
    a truncated record is honest about what it contains, and a rewritten one is
    not.

    The writer deliberately cannot label an outcome. Outcomes are measured off
    the robot after the run, by a human at a balance, so they are recorded
    through ``complete`` -- a separate act, at a separate time, by a named
    person.
    """

    def __init__(self, root: Path, record: EpisodeRecord) -> None:
        self._directory = Path(root) / record.episode_id
        self._directory.mkdir(parents=True, exist_ok=True)
        self._record = record
        self._frames = 0
        self._events: list[SafetyEvent] = list(record.safety_events)
        self._closed = False
        self._flush()

    @property
    def directory(self) -> Path:
        return self._directory

    @property
    def frame_count(self) -> int:
        return self._frames

    @property
    def record(self) -> EpisodeRecord:
        return self._record

    def _flush(self) -> None:
        from dataclasses import replace

        self._record = replace(
            self._record,
            frame_count=self._frames,
            safety_events=tuple(self._events),
        )
        payload = dict(self._record.as_payload())
        payload["record_digest"] = _digest(payload)
        _write_atomic(self._directory / MANIFEST_FILE, payload)

    def append(self, frame: Frame) -> None:
        if self._closed:
            raise RuntimeError(
                "this episode is complete; a frame appended after the outcome "
                "was measured would change what the measurement refers to"
            )
        _append(self._directory / FRAMES_FILE, frame.as_payload())
        self._frames += 1

    def note(self, event: SafetyEvent) -> None:
        """Record a safety event immediately, even mid-run.

        Events are flushed on arrival rather than at close, because the events
        worth having are exactly the ones that precede an abnormal end.
        """
        _append(self._directory / EVENTS_FILE, event.as_payload())
        self._events.append(event)
        self._flush()

    def testify(self, testimony: HumanTestimony) -> None:
        from dataclasses import replace

        self._record = replace(
            self._record, testimony=self._record.testimony + (testimony,)
        )
        self._flush()

    def complete(self, outcome: EpisodeOutcome) -> EpisodeRecord:
        """Attach the measured outcome and seal the record."""
        from dataclasses import replace

        self._record = replace(self._record, outcome=outcome)
        self._closed = True
        self._flush()
        return self._record

    def frames(self) -> Iterator[Mapping[str, object]]:
        """Replay what was written, for failure analysis and training export."""
        path = self._directory / FRAMES_FILE
        if not path.exists():
            return iter(())

        def _iterate() -> Iterator[Mapping[str, object]]:
            with path.open("r", encoding="utf-8") as handle:
                for number, line in enumerate(handle, start=1):
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        yield json.loads(text)
                    except ValueError as exc:
                        raise ValueError(
                            f"{path}:{number} is unreadable: {exc}. A frame "
                            "that cannot be read is not skipped, because a "
                            "quietly shortened episode reads as a successful "
                            "one"
                        ) from exc

        return _iterate()
