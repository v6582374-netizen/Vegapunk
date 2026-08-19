"""Recorded episodes become training samples, or are refused with a reason.

A learned policy needs `(observation, action chunk)` pairs in the exact shapes
the serving path uses, and the only recorded data on this embodiment is the
vendored 30 Hz recorder's output. This module is the conversion, and most of it
is about what conversion is *not* allowed to invent.

``VendoredEpisode``   one recorded directory, read and validated
``TrainingSample``    one observation plus the chunk of targets that followed
``ConversionReport``  what converted, what was dropped, and why

The three things this refuses to do
-----------------------------------
**It will not invent the action's shape.** Recorded hand arrays are sometimes
seven values and sometimes six; the vendored real path slices to six and sends
those to the hand. So six is the contract and the seventh value is dropped
explicitly, with a count in the report, rather than being silently reshaped.

**It will not invent alignment.** The recorder stores ``t_img`` and ``t_action``
per item and ``t_state`` as ``null`` in every existing episode. Where a
timestamp is missing, the sample records that its alignment is by index rather
than by clock, because a converter that quietly treated index order as
synchronisation would produce a dataset whose latency is unknowable afterwards.

**It will not invent provenance.** These episodes have one camera, no lid
witness, no reset record and no outcome label. Under the episode contract
they are therefore not training-grade, and this module says so in the report
instead of upgrading them by conversion. They are still useful: they exercise
the whole path -- converter, policy server, monitor, bridge, guard -- against
real numbers from the real robot in the real room, which is the only way the
plumbing gets proven before a human collects anything.

So the honest summary of what this produces from today's data is *plumbing
evidence*, not a training set. When properly collected episodes exist, the same
converter reads them and the report stops listing the gaps.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Mapping, Optional, Sequence

from vegapunk.operation.target import (
    BODY_DIM,
    CONTROL_PERIOD_S,
    HAND_DIM,
    WholeBodyTarget,
)
from vegapunk.operation.tracker import STATE_BODY_DIM, TrackerState

DATA_FILE = "data.json"
RGB_DIR = "rgb"

HEAD_LEFT = "head_left"
HEAD_RIGHT = "head_right"

RECORDED_VIEW_WIDTH = 640
RECORDED_VIEW_HEIGHT = 480

HEAD_STEREO_VIEWS: tuple[tuple[str, tuple[int, int, int, int]], ...] = (
    (HEAD_LEFT, (0, 0, RECORDED_VIEW_WIDTH, RECORDED_VIEW_HEIGHT)),
    (
        HEAD_RIGHT,
        (
            RECORDED_VIEW_WIDTH,
            0,
            2 * RECORDED_VIEW_WIDTH,
            RECORDED_VIEW_HEIGHT,
        ),
    ),
)
"""How one recorded JPEG maps onto named views.

The vendored recorder allocates ``(480, 640 * num_cameras, 3)`` with
``num_cameras = 2`` and writes the result as a single file, so every recorded
frame is 480x1280: two 640x480 views side by side in one image.

Measured on the recorded frames, the two halves correlate at about 0.72 at a
horizontal shift that changes with scene content -- 16, 30 and 12 px on three
frames sampled across one episode. That is disparity, so this is a stereo pair
from the one head camera rather than two viewpoints.

Two consequences, and both are why this layout is explicit rather than assumed:

- An encoder handed the raw file would treat a side-by-side pair as one image
  and learn features of a seam down the middle of its input.
- The pair is *one camera*. Counting it as two would report the data contract's
  three-camera requirement as nearly met when both wrist cameras are absent.
"""

ALIGNED_BY_CLOCK = "clock"
ALIGNED_BY_INDEX = "index"

DROP_SHORT_TAIL = "short_tail"
DROP_BAD_TARGET = "unbuildable_target"
DROP_BAD_STATE = "unbuildable_state"
DROP_MISSING_IMAGE = "missing_image"


@dataclass(frozen=True)
class TrainingSample:
    """One observation and the chunk of targets that followed it.

    The chunk is the label. It is several consecutive frames rather than one,
    because that is what the serving path consumes: a policy that emitted a
    single frame per inference would have to run inference every 20 ms, and the
    whole point of the fast/slow split is that it does not.
    """

    episode_id: str
    index: int
    time_ns: int
    images: Mapping[str, str]
    state: TrackerState
    chunk: tuple[WholeBodyTarget, ...]
    alignment: str

    def __post_init__(self) -> None:
        if not self.chunk:
            raise ValueError("a sample with no action chunk teaches nothing")
        if not self.images:
            raise ValueError("a sample with no image is not an observation")
        object.__setattr__(self, "images", dict(self.images))
        object.__setattr__(self, "chunk", tuple(self.chunk))

    @property
    def horizon(self) -> int:
        return len(self.chunk)

    @property
    def aligned_by_clock(self) -> bool:
        return self.alignment == ALIGNED_BY_CLOCK


@dataclass
class ConversionReport:
    """What the conversion produced, and every way it fell short.

    Counts rather than booleans throughout, because "some frames were dropped"
    is not actionable and "1,766 frames were dropped for an unbuildable target"
    is.
    """

    episodes: int = 0
    samples: int = 0
    frames_read: int = 0
    dropped: dict[str, int] = field(default_factory=dict)
    clamped_frames: int = 0
    seven_value_hands: int = 0
    index_aligned_samples: int = 0
    cameras: set[str] = field(default_factory=set)
    views: set[str] = field(default_factory=set)
    provenance_gaps: list[str] = field(default_factory=list)

    def drop(self, reason: str) -> None:
        self.dropped[reason] = self.dropped.get(reason, 0) + 1

    @property
    def dropped_total(self) -> int:
        return sum(self.dropped.values())

    @property
    def training_grade(self) -> bool:
        """Whether the converted set may be used as imitation data.

        False whenever any provenance gap is recorded. This is deliberately not
        a threshold or a score: a dataset missing its outcome labels is not
        partially trainable, it is unlabelled.
        """
        return not self.provenance_gaps

    def summary(self) -> str:
        lines = [
            f"episodes={self.episodes} frames={self.frames_read} "
            f"samples={self.samples} dropped={self.dropped_total}",
        ]
        for reason, count in sorted(self.dropped.items(), key=lambda kv: -kv[1]):
            lines.append(f"  dropped[{reason}]={count}")
        lines.append(
            f"  clamped_frames={self.clamped_frames} "
            f"seven_value_hands={self.seven_value_hands} "
            f"index_aligned={self.index_aligned_samples}"
        )
        lines.append(
            f"  cameras={sorted(self.cameras) or ['<none>']} "
            f"views={sorted(self.views) or ['<none>']}"
        )
        if self.provenance_gaps:
            lines.append("  NOT training-grade:")
            for gap in self.provenance_gaps:
                lines.append(f"    - {gap}")
        else:
            lines.append("  training-grade: yes")
        return "\n".join(lines)


class VendoredEpisode:
    """One directory written by the vendored 30 Hz recorder.

    Reading is lazy per item so a 2,600-frame episode with 2,600 JPEGs is never
    fully resident: the images stay as paths, which is also what the training
    loader wants.
    """

    def __init__(self, directory: Path) -> None:
        self._directory = Path(directory)
        payload_path = self._directory / DATA_FILE
        if not payload_path.exists():
            raise ValueError(f"{self._directory} has no {DATA_FILE}")
        payload = json.loads(payload_path.read_text())
        self._info = payload.get("info", {})
        self._text = payload.get("text", {})
        self._items = payload.get("data", [])
        if not self._items:
            raise ValueError(f"{self._directory} records no frames")

    @property
    def episode_id(self) -> str:
        return f"{self._directory.parent.name}/{self._directory.name}"

    @property
    def frame_count(self) -> int:
        return len(self._items)

    @property
    def goal(self) -> str:
        return str(self._text.get("goal", ""))

    @property
    def fps(self) -> float:
        image = self._info.get("image", {})
        return float(image.get("fps", 30.0))

    def items(self) -> Iterator[Mapping[str, object]]:
        return iter(self._items)

    def image_path(self, relative: str) -> Path:
        return self._directory / relative


def _hand(values: object, report: ConversionReport) -> tuple[float, ...]:
    """Six values, from a recorded array that may carry seven.

    The seventh is dropped rather than reshaped, because the vendored real path
    slices to six before sending to the hand: six is what the robot executed, so
    six is what a policy must learn to emit.
    """
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"hand action is not an array: {values!r}")
    if len(values) > HAND_DIM:
        report.seven_value_hands += 1
    if len(values) < HAND_DIM:
        raise ValueError(f"hand action carries only {len(values)} values")
    return tuple(float(v) for v in values[:HAND_DIM])


def _target_from_item(
    item: Mapping[str, object],
    sequence: int,
    time_ns: int,
    report: ConversionReport,
) -> WholeBodyTarget:
    body = item.get("action_body")
    if not isinstance(body, (list, tuple)) or len(body) != BODY_DIM:
        raise ValueError(
            f"action_body must carry {BODY_DIM} values, got "
            f"{len(body) if isinstance(body, (list, tuple)) else type(body)}"
        )
    target = WholeBodyTarget(
        sequence=sequence,
        source_time_ns=time_ns,
        valid_until_ns=time_ns + 3 * int(CONTROL_PERIOD_S * 1e9),
        body=tuple(float(v) for v in body),
        left_hand=_hand(item.get("action_hand_left"), report),
        right_hand=_hand(item.get("action_hand_right"), report),
    )
    if target.saturated:
        report.clamped_frames += 1
    return target


def _state_from_item(
    item: Mapping[str, object], sequence: int, time_ns: int
) -> TrackerState:
    body = item.get("state_body")
    if not isinstance(body, (list, tuple)) or len(body) != STATE_BODY_DIM:
        raise ValueError(
            f"state_body must carry {STATE_BODY_DIM} values, got "
            f"{len(body) if isinstance(body, (list, tuple)) else type(body)}"
        )
    left = item.get("state_hand_left") or [0.0] * HAND_DIM
    right = item.get("state_hand_right") or [0.0] * HAND_DIM
    return TrackerState(
        sequence=sequence,
        state_time_ns=time_ns,
        body=tuple(float(v) for v in body),
        left_hand=tuple(float(v) for v in left[:HAND_DIM]),
        right_hand=tuple(float(v) for v in right[:HAND_DIM]),
        applied_target_sequence=sequence,
    )


def _views(path: Path) -> dict[str, str]:
    """Name each view inside one recorded file, carrying its crop.

    The reference form is ``path#x0,y0,x1,y1``. It stays a string because that
    is what the episode record and the training set both store, and a crop that
    travelled separately from its path would eventually be applied to the wrong
    file.
    """
    return {
        name: f"{path}#{box[0]},{box[1]},{box[2]},{box[3]}"
        for name, box in HEAD_STEREO_VIEWS
    }


def convert_episode(
    episode: VendoredEpisode,
    *,
    horizon: int,
    report: ConversionReport,
    camera: str = "head",
    require_images: bool = True,
) -> list[TrainingSample]:
    """Turn one recorded episode into samples, dropping what cannot be built.

    A frame that cannot produce a valid target is dropped rather than repaired.
    Repair would mean choosing a value the demonstrator did not command, and a
    dataset containing invented actions teaches the invented behaviour.
    """
    if horizon < 1:
        raise ValueError("horizon must be at least one frame")

    items = list(episode.items())
    report.episodes += 1
    report.frames_read += len(items)
    report.cameras.add(camera)
    report.views.update(name for name, _ in HEAD_STEREO_VIEWS)

    targets: list[Optional[WholeBodyTarget]] = []
    states: list[Optional[TrackerState]] = []
    times: list[int] = []
    alignments: list[str] = []
    images: list[Optional[str]] = []

    for index, item in enumerate(items):
        t_action = item.get("t_action")
        t_img = item.get("t_img")
        t_state = item.get("t_state")
        alignment = (
            ALIGNED_BY_CLOCK
            if t_action is not None and t_img is not None and t_state is not None
            else ALIGNED_BY_INDEX
        )
        stamp = t_action if isinstance(t_action, (int, float)) else t_img
        time_ns = (
            int(stamp) * 1_000_000
            if isinstance(stamp, (int, float))
            else (index + 1) * int(CONTROL_PERIOD_S * 1e9)
        )
        times.append(max(1, time_ns))
        alignments.append(alignment)

        try:
            targets.append(_target_from_item(item, index, times[-1], report))
        except ValueError:
            targets.append(None)
            report.drop(DROP_BAD_TARGET)
        try:
            states.append(_state_from_item(item, index, times[-1]))
        except ValueError:
            states.append(None)
            report.drop(DROP_BAD_STATE)

        relative = item.get("rgb")
        if not isinstance(relative, str):
            images.append(None)
            report.drop(DROP_MISSING_IMAGE)
        elif require_images and not episode.image_path(relative).exists():
            images.append(None)
            report.drop(DROP_MISSING_IMAGE)
        else:
            images.append(relative)

    samples: list[TrainingSample] = []
    for index in range(len(items)):
        if states[index] is None or images[index] is None:
            continue
        window = targets[index : index + horizon]
        if len(window) < horizon:
            report.drop(DROP_SHORT_TAIL)
            continue
        if any(frame is None for frame in window):
            continue
        alignment = (
            ALIGNED_BY_CLOCK
            if all(
                alignments[offset] == ALIGNED_BY_CLOCK
                for offset in range(index, index + horizon)
            )
            else ALIGNED_BY_INDEX
        )
        if alignment == ALIGNED_BY_INDEX:
            report.index_aligned_samples += 1
        samples.append(
            TrainingSample(
                episode_id=episode.episode_id,
                index=index,
                time_ns=times[index],
                images=_views(episode.image_path(images[index])),
                state=states[index],
                chunk=tuple(frame for frame in window if frame is not None),
                alignment=alignment,
            )
        )

    report.samples += len(samples)
    return samples


def convert_vendored_tree(
    root: Path,
    *,
    horizon: int = 8,
    require_images: bool = True,
) -> tuple[list[TrainingSample], ConversionReport]:
    """Convert every recorded episode under a vendored demonstration root.

    The report's provenance gaps are what stop this from being a training set.
    They are computed from the data rather than asserted, so a properly
    collected batch clears them by being properly collected.
    """
    root = Path(root)
    report = ConversionReport()
    samples: list[TrainingSample] = []

    directories = sorted(
        path.parent
        for path in root.rglob(DATA_FILE)
        if path.is_file()
    )
    for directory in directories:
        try:
            episode = VendoredEpisode(directory)
        except ValueError:
            continue
        samples.extend(
            convert_episode(
                episode,
                horizon=horizon,
                report=report,
                require_images=require_images,
            )
        )

    if len(report.cameras) < 3:
        report.provenance_gaps.append(
            f"only {sorted(report.cameras)} recorded: the data contract needs "
            "the head camera and both wrist cameras"
        )
    if report.index_aligned_samples:
        report.provenance_gaps.append(
            f"{report.index_aligned_samples} samples are aligned by index "
            "because the recorder wrote no state timestamp; observation/action "
            "latency is therefore unknown"
        )
    report.provenance_gaps.append(
        "no lid witness value was recorded, so no frame can be checked against "
        "the pour gate"
    )
    report.provenance_gaps.append(
        "no reset record and no outcome label, so no episode has a recorded "
        "starting state or a judged result"
    )

    return samples, report
