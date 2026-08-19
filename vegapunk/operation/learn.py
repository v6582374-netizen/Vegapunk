"""The learning shape: recorded samples become a servable fast policy.

The architectural sample splits its VLA into a slow vision-language system that
emits an intent latent below 5 Hz and a small fast policy that turns that intent
plus live observations into whole-body action chunks at 50 Hz. This module is the
fast half, because it is the half that must exist first: the fast policy is what
occupies the seam the tracker consumes, and a slow system with nothing to drive
is untestable.

``Normalizer``        per-channel statistics, carried inside the checkpoint
``ChunkDataset``      samples flattened into (observation, chunk) tensors
``FastPolicyNet``     the network: state + image features -> one action chunk
``TrainingConfig``    what a run was configured with, recorded with its result
``TrainingResult``    losses, and whether the checkpoint may be served
``train``             the loop
``LearnedFastPolicy`` the checkpoint, wearing the ``FastPolicy`` protocol

Three refusals shape this module.

**A checkpoint trained on non-training-grade data cannot be marked deployable.**
The dataset converter records exactly why a set fell short -- missing wrist
cameras, index-aligned observations, no lid witness, no measured outcomes -- and
those gaps travel into the checkpoint. A file that cannot say what it was trained
on is a file somebody will serve by accident.

**A policy never emits a raw number to the robot.** Its output is denormalized
and then handed to ``WholeBodyTarget``, whose construction is the validation. A
network that could bypass that would be the one producer able to write an
unexecutable frame, which is precisely what the contract exists to prevent.

**Normalization statistics are part of the checkpoint, not the training script.**
A policy served with different statistics than it was trained with is silently
wrong: every output is scaled and offset, and nothing raises.

On the slow system
------------------
Deliberately absent. The instruction for this loop is fixed, so there is nothing
for a language model to interpret, and the intent latent is optional in the
serving path (``PolicyServer`` already tolerates ``None``). When a slow system is
added it trains against the same samples and reaches the fast policy through
``SlowIntent`` -- the seam is already there, unused rather than unplanned.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Sequence

from vegapunk.operation.dataset import ConversionReport, TrainingSample
from vegapunk.operation.policy import ActionChunk, Observation, SlowIntent
from vegapunk.operation.target import (
    BODY_DIM,
    BODY_JOINTS,
    CONTROL_PERIOD_S,
    G1_JOINT_LIMITS_RAD,
    HAND_DIM,
    HAND_LIMITS_RAD,
    MAX_ROOT_SPEED_MPS,
    MAX_ROOT_TILT_RAD,
    MAX_ROOT_YAW_RATE_RPS,
    ROOT_HEIGHT_RANGE_M,
    ROOT_HEIGHT,
    ROOT_YAW_RATE,
    WholeBodyTarget,
)
from vegapunk.operation.tracker import STATE_BODY_DIM, TrackerState

ACTION_DIM = BODY_DIM + 2 * HAND_DIM
"""47: one frame of the whole-body target contract, flattened."""

STATE_DIM = STATE_BODY_DIM + 2 * HAND_DIM
"""46: one frame of tracker feedback, flattened."""

CHECKPOINT_FILE = "policy.pt"
MANIFEST_FILE = "checkpoint.json"


def _require_torch():
    """Import torch lazily, with an honest error.

    Training needs torch; the contract, bridge, monitor and session do not. A
    module-level import would make the whole harness unimportable on a machine
    that only ever runs the actuation path, which is the machine that matters
    most.
    """
    try:
        import torch  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "training requires torch. The actuation path does not: install "
            "torch only where policies are trained or served."
        ) from exc
    return torch


def _flatten_target(target: WholeBodyTarget) -> list[float]:
    return list(target.body) + list(target.left_hand) + list(target.right_hand)


def _flatten_state(state: TrackerState) -> list[float]:
    return list(state.body) + list(state.left_hand) + list(state.right_hand)


@dataclass(frozen=True)
class Normalizer:
    """Per-channel mean and scale, computed from the training set.

    Scale is a standard deviation with a floor, not a range. Several channels in
    this contract are constant across every recorded frame -- ankle roll targets
    that never move, a root height that varies by three centimetres -- and
    dividing by their spread would amplify sensor noise into the loudest signal
    the network sees.
    """

    mean: tuple[float, ...]
    scale: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.mean) != len(self.scale):
            raise ValueError("mean and scale must describe the same channels")
        if not self.mean:
            raise ValueError("a normalizer with no channels normalizes nothing")
        for value in self.scale:
            if value <= 0:
                raise ValueError("every scale must be positive")

    @classmethod
    def fit(
        cls, rows: Sequence[Sequence[float]], *, floor: float = 1e-3
    ) -> "Normalizer":
        if not rows:
            raise ValueError("cannot fit a normalizer on no rows")
        width = len(rows[0])
        count = len(rows)
        means = [0.0] * width
        for row in rows:
            if len(row) != width:
                raise ValueError("every row must have the same width")
            for index, value in enumerate(row):
                means[index] += value
        means = [total / count for total in means]
        variances = [0.0] * width
        for row in rows:
            for index, value in enumerate(row):
                delta = value - means[index]
                variances[index] += delta * delta
        scales = [
            max(math.sqrt(total / count), floor) for total in variances
        ]
        return cls(mean=tuple(means), scale=tuple(scales))

    def normalize(self, row: Sequence[float]) -> list[float]:
        return [
            (value - mean) / scale
            for value, mean, scale in zip(row, self.mean, self.scale)
        ]

    def denormalize(self, row: Sequence[float]) -> list[float]:
        return [
            value * scale + mean
            for value, mean, scale in zip(row, self.mean, self.scale)
        ]

    def as_payload(self) -> dict[str, object]:
        return {"mean": list(self.mean), "scale": list(self.scale)}

    @classmethod
    def from_payload(cls, payload: dict) -> "Normalizer":
        return cls(
            mean=tuple(float(v) for v in payload["mean"]),
            scale=tuple(float(v) for v in payload["scale"]),
        )


class ImageEncoder:
    """The vision seam, and the reason it is a seam.

    Serving reads images from a live camera; training reads them from disk. Both
    reach the network through this one interface, so the two paths cannot drift
    into different preprocessing -- which is the classic way a policy that
    trained well fails on the robot while every test still passes.

    The default implementation is deliberately a placeholder that reports its own
    dimensionality and produces zeros: it keeps the network shape honest before a
    real encoder exists, and because it is obviously inert nobody can mistake its
    output for learned features.
    """

    def __init__(self, feature_dim: int = 0) -> None:
        if feature_dim < 0:
            raise ValueError("feature_dim cannot be negative")
        self._feature_dim = feature_dim

    @property
    def feature_dim(self) -> int:
        return self._feature_dim

    @property
    def identity(self) -> str:
        return "inert" if self._feature_dim == 0 else f"zeros[{self._feature_dim}]"

    def encode(self, images) -> list[float]:  # noqa: ANN001 - accepts either source
        return [0.0] * self._feature_dim


@dataclass(frozen=True)
class TrainingConfig:
    """What one training run was configured with.

    Recorded alongside the result because a loss curve without its configuration
    cannot be compared to the next one, and comparing runs is the entire point of
    a pilot.
    """

    horizon: int
    hidden: int = 512
    layers: int = 3
    epochs: int = 20
    batch_size: int = 64
    learning_rate: float = 3e-4
    weight_decay: float = 1e-4
    validation_fraction: float = 0.2
    seed: int = 0

    def __post_init__(self) -> None:
        if self.horizon < 1:
            raise ValueError("horizon must be at least one frame")
        if self.hidden < 1 or self.layers < 1:
            raise ValueError("the network needs at least one hidden layer")
        if self.epochs < 1:
            raise ValueError("training needs at least one epoch")
        if self.batch_size < 1:
            raise ValueError("batch_size must be positive")
        if not 0.0 <= self.validation_fraction < 1.0:
            raise ValueError("validation_fraction must be in [0, 1)")

    def as_payload(self) -> dict[str, object]:
        return {
            "horizon": self.horizon,
            "hidden": self.hidden,
            "layers": self.layers,
            "epochs": self.epochs,
            "batch_size": self.batch_size,
            "learning_rate": self.learning_rate,
            "weight_decay": self.weight_decay,
            "validation_fraction": self.validation_fraction,
            "seed": self.seed,
        }


@dataclass
class TrainingResult:
    """What a run produced, and whether the checkpoint may be served.

    ``deployable`` is false whenever the dataset carried a provenance gap, no
    matter how low the loss went. A policy that fits an unlabelled dataset has
    learned that dataset; it has not been shown to do the task, because nothing
    in the dataset records whether the task was done.
    """

    config: TrainingConfig
    train_losses: list[float] = field(default_factory=list)
    validation_losses: list[float] = field(default_factory=list)
    train_samples: int = 0
    validation_samples: int = 0
    provenance_gaps: list[str] = field(default_factory=list)
    episodes: tuple[str, ...] = ()

    @property
    def final_train_loss(self) -> float:
        return self.train_losses[-1] if self.train_losses else float("nan")

    @property
    def final_validation_loss(self) -> float:
        return (
            self.validation_losses[-1]
            if self.validation_losses
            else float("nan")
        )

    @property
    def deployable(self) -> tuple[bool, str]:
        if self.provenance_gaps:
            return False, (
                "trained on data that is not training-grade: "
                + "; ".join(self.provenance_gaps)
            )
        if not self.validation_losses:
            return False, "no held-out episodes were evaluated"
        return True, ""

    def summary(self) -> str:
        ok, why = self.deployable
        lines = [
            f"train={self.train_samples} val={self.validation_samples} "
            f"epochs={len(self.train_losses)}",
            f"final train loss={self.final_train_loss:.6f} "
            f"val loss={self.final_validation_loss:.6f}",
            f"deployable={ok}" + (f" ({why})" if why else ""),
        ]
        return "\n".join(lines)


def build_network(observation_dim: int, output_dim: int, config: TrainingConfig):
    """A plain MLP over state and image features.

    Chosen because it is the smallest thing that can occupy the serving seam
    honestly. The sample's fast policy is a flow-matching model, which earns its
    complexity on multimodal demonstrations; with no training-grade dataset in
    existence yet, a flow model here would be an untested guess wrapped around an
    untested dataset. The architecture is the easiest part of this system to
    replace -- the contract, bridge, monitor and record are not -- so it is
    deliberately the part left simplest.
    """
    torch = _require_torch()
    from torch import nn

    widths = [observation_dim] + [config.hidden] * config.layers
    modules: list[object] = []
    for inp, out in zip(widths[:-1], widths[1:]):
        modules.append(nn.Linear(inp, out))
        modules.append(nn.SiLU())
    modules.append(nn.Linear(widths[-1], output_dim))
    return nn.Sequential(*modules)


class ChunkDataset:
    """Samples flattened into normalized (observation, chunk) rows.

    Built eagerly in memory. Ten thousand frames of 47 floats is a few megabytes,
    so streaming would add a failure mode -- a half-read episode -- to buy nothing
    at this scale.
    """

    def __init__(
        self,
        samples: Sequence[TrainingSample],
        *,
        horizon: int,
        encoder: Optional[ImageEncoder] = None,
        state_normalizer: Optional[Normalizer] = None,
        action_normalizer: Optional[Normalizer] = None,
    ) -> None:
        if not samples:
            raise ValueError("cannot build a dataset from no samples")
        usable = [s for s in samples if s.horizon >= horizon]
        if not usable:
            raise ValueError(
                f"no sample carries a chunk of {horizon} frames; the longest is "
                f"{max(s.horizon for s in samples)}"
            )
        self._horizon = horizon
        self._encoder = encoder or ImageEncoder()
        self._samples = usable

        states = [_flatten_state(s.state) for s in usable]
        actions: list[list[float]] = []
        for sample in usable:
            row: list[float] = []
            for frame in sample.chunk[:horizon]:
                row.extend(_flatten_target(frame))
            actions.append(row)

        self._state_normalizer = state_normalizer or Normalizer.fit(states)
        # Action statistics are fitted per channel of a single frame and reused
        # across the chunk: a channel's units do not change because it is the
        # third step of a chunk rather than the first, and fitting per position
        # would make the same joint carry different scales at different offsets.
        per_frame = [
            row[offset * ACTION_DIM : (offset + 1) * ACTION_DIM]
            for row in actions
            for offset in range(horizon)
        ]
        self._action_normalizer = action_normalizer or Normalizer.fit(per_frame)

        self._observations = [
            self._state_normalizer.normalize(state)
            + self._encoder.encode(sample.images)
            for state, sample in zip(states, usable)
        ]
        self._targets = [
            [
                value
                for offset in range(horizon)
                for value in self._action_normalizer.normalize(
                    row[offset * ACTION_DIM : (offset + 1) * ACTION_DIM]
                )
            ]
            for row in actions
        ]

    def __len__(self) -> int:
        return len(self._observations)

    @property
    def horizon(self) -> int:
        return self._horizon

    @property
    def observation_dim(self) -> int:
        return len(self._observations[0])

    @property
    def output_dim(self) -> int:
        return len(self._targets[0])

    @property
    def state_normalizer(self) -> Normalizer:
        return self._state_normalizer

    @property
    def action_normalizer(self) -> Normalizer:
        return self._action_normalizer

    @property
    def encoder(self) -> ImageEncoder:
        return self._encoder

    @property
    def episode_ids(self) -> tuple[str, ...]:
        seen: list[str] = []
        for sample in self._samples:
            if sample.episode_id not in seen:
                seen.append(sample.episode_id)
        return tuple(seen)

    def tensors(self):
        torch = _require_torch()
        return (
            torch.tensor(self._observations, dtype=torch.float32),
            torch.tensor(self._targets, dtype=torch.float32),
        )

    def split_by_episode(
        self, validation_fraction: float
    ) -> tuple[list[int], list[int]]:
        """Hold out whole episodes, never individual frames.

        Consecutive frames of one demonstration are near-duplicates at 30 Hz, so
        a random frame split puts a sample's own neighbours in the validation
        set. The resulting loss measures interpolation between adjacent frames
        and looks excellent regardless of whether anything generalises.
        """
        episodes = self.episode_ids
        if len(episodes) < 2 or validation_fraction <= 0:
            return list(range(len(self))), []
        held = max(1, int(round(len(episodes) * validation_fraction)))
        validation_ids = set(episodes[-held:])
        train_indices = [
            index
            for index, sample in enumerate(self._samples)
            if sample.episode_id not in validation_ids
        ]
        validation_indices = [
            index
            for index, sample in enumerate(self._samples)
            if sample.episode_id in validation_ids
        ]
        if not train_indices:
            return list(range(len(self))), []
        return train_indices, validation_indices


def train(
    dataset: ChunkDataset,
    config: TrainingConfig,
    report: Optional[ConversionReport] = None,
    *,
    progress: Optional[Callable[[int, float, float], None]] = None,
) -> tuple[object, TrainingResult]:
    """Fit the fast policy. Returns the network and what the run proved.

    The provenance gaps from the conversion travel into the result untouched, so
    a checkpoint can never lose the reason it is not deployable somewhere between
    the dataset and the file.
    """
    torch = _require_torch()

    torch.manual_seed(config.seed)
    observations, targets = dataset.tensors()
    train_indices, validation_indices = dataset.split_by_episode(
        config.validation_fraction
    )

    network = build_network(
        dataset.observation_dim, dataset.output_dim, config
    )
    optimizer = torch.optim.AdamW(
        network.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    loss_fn = torch.nn.MSELoss()

    train_x = observations[train_indices]
    train_y = targets[train_indices]
    has_validation = bool(validation_indices)
    if has_validation:
        val_x = observations[validation_indices]
        val_y = targets[validation_indices]

    result = TrainingResult(
        config=config,
        train_samples=len(train_indices),
        validation_samples=len(validation_indices),
        provenance_gaps=list(report.provenance_gaps) if report else [],
        episodes=dataset.episode_ids,
    )

    generator = torch.Generator().manual_seed(config.seed)
    for epoch in range(config.epochs):
        network.train()
        order = torch.randperm(len(train_x), generator=generator)
        total = 0.0
        batches = 0
        for start in range(0, len(order), config.batch_size):
            batch = order[start : start + config.batch_size]
            optimizer.zero_grad()
            predicted = network(train_x[batch])
            loss = loss_fn(predicted, train_y[batch])
            loss.backward()
            optimizer.step()
            total += float(loss.detach())
            batches += 1
        train_loss = total / max(batches, 1)
        result.train_losses.append(train_loss)

        validation_loss = float("nan")
        if has_validation:
            network.eval()
            with torch.no_grad():
                validation_loss = float(loss_fn(network(val_x), val_y))
            result.validation_losses.append(validation_loss)

        if progress is not None:
            progress(epoch, train_loss, validation_loss)

    return network, result


def _encoder_spec(encoder: object) -> dict[str, object]:
    """Describe an encoder well enough to rebuild it.

    Only two kinds exist, and they are distinguished by capability rather than
    by class name: an encoder that names views reads images, and one that does
    not produces zeros.
    """
    views = getattr(encoder, "views", ())
    if not views:
        return {"kind": "inert", "feature_dim": int(encoder.feature_dim)}  # type: ignore[attr-defined]
    return {
        "kind": "vision",
        "views": list(views),
        "input_size": int(getattr(encoder, "input_size", 224)),
        "identity": encoder.identity,  # type: ignore[attr-defined]
        "feature_dim": int(encoder.feature_dim),  # type: ignore[attr-defined]
    }


def _encoder_from_spec(spec: object, feature_dim: int):
    """Rebuild the encoder a checkpoint was trained with.

    Refuses to substitute. A checkpoint trained on image features and loaded
    with an inert encoder would receive zeros where it learned to read a scene:
    every tensor shape matches, nothing raises, and the policy acts on a view of
    the world that is uniformly black. That is the worst available failure, so a
    vision checkpoint whose encoder cannot be rebuilt raises instead.
    """
    if not isinstance(spec, dict) or spec.get("kind") != "vision":
        return ImageEncoder(feature_dim)
    from vegapunk.operation.vision import VisionEncoder  # noqa: PLC0415

    encoder = VisionEncoder(
        views=tuple(str(v) for v in spec.get("views", ())),
        size=int(spec.get("input_size", 224)),
    )
    if encoder.feature_dim != feature_dim:
        raise ValueError(
            f"this checkpoint was trained with {feature_dim} image features but "
            f"the rebuilt encoder produces {encoder.feature_dim}. Serving it "
            "would feed the policy a different observation than it learned."
        )
    return encoder


def save_checkpoint(
    directory: Path,
    network: object,
    dataset: ChunkDataset,
    result: TrainingResult,
) -> Path:
    """Write the network next to everything needed to serve it honestly."""
    torch = _require_torch()

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    torch.save(network.state_dict(), directory / CHECKPOINT_FILE)

    deployable, why = result.deployable
    manifest = {
        "horizon": dataset.horizon,
        "observation_dim": dataset.observation_dim,
        "output_dim": dataset.output_dim,
        "action_dim": ACTION_DIM,
        "state_normalizer": dataset.state_normalizer.as_payload(),
        "action_normalizer": dataset.action_normalizer.as_payload(),
        "image_encoder": dataset.encoder.identity,
        "image_feature_dim": dataset.encoder.feature_dim,
        # Enough to rebuild the *same* encoder, not merely one of the same
        # width. A checkpoint trained on ResNet features and served with zeros
        # has identical tensor shapes and produces confident nonsense.
        "image_encoder_spec": _encoder_spec(dataset.encoder),
        "config": result.config.as_payload(),
        "train_samples": result.train_samples,
        "validation_samples": result.validation_samples,
        "final_train_loss": result.final_train_loss,
        "final_validation_loss": result.final_validation_loss,
        "episodes": list(result.episodes),
        "provenance_gaps": list(result.provenance_gaps),
        "deployable": deployable,
        "not_deployable_because": why,
    }
    path = directory / MANIFEST_FILE
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return directory


def project_onto_executable(
    values: Sequence[float],
) -> tuple[list[float], float]:
    """Clip a network's continuous output onto the executable set.

    Returns the projected values and the largest distance any channel had to
    move.

    This exists because a regression network's output is an *estimate*, not an
    authored value. Nothing in an unbounded linear output layer knows that a
    finger stops at zero, so a policy trained on demonstrations where the pinky
    rests at 0.0 will predict -0.06 on some frames purely from fitting error.
    That is not a producer trying to do something impossible; it is a continuous
    function landing a few hundredths outside a box.

    The contract deliberately refuses such a frame, and it is right to: it cannot
    tell a network's fitting error from a hand-authored mistake, and silently
    accepting an out-of-range pose is how an unexecutable command reaches a
    robot. So the projection belongs *here*, in the one producer that knows its
    own output is an estimate. A hand-written producer gets no such courtesy.

    The distance is returned rather than swallowed. Small projections are the
    normal cost of regression; a policy whose outputs need moving by a radian has
    learned something this embodiment cannot execute, and the loss curve will
    never say so.
    """
    projected = list(values)
    worst = 0.0

    def clip(index: int, low: float, high: float) -> None:
        nonlocal worst
        value = projected[index]
        if value < low:
            worst = max(worst, low - value)
            projected[index] = low
        elif value > high:
            worst = max(worst, value - high)
            projected[index] = high

    # Root speed is a magnitude, so it is scaled rather than clipped per axis:
    # clipping vx and vy independently would rotate the commanded heading.
    speed = math.hypot(projected[0], projected[1])
    if speed > MAX_ROOT_SPEED_MPS:
        worst = max(worst, speed - MAX_ROOT_SPEED_MPS)
        scale = MAX_ROOT_SPEED_MPS / speed
        projected[0] *= scale
        projected[1] *= scale

    clip(ROOT_HEIGHT, *ROOT_HEIGHT_RANGE_M)
    clip(3, -MAX_ROOT_TILT_RAD, MAX_ROOT_TILT_RAD)
    clip(4, -MAX_ROOT_TILT_RAD, MAX_ROOT_TILT_RAD)
    clip(ROOT_YAW_RATE, -MAX_ROOT_YAW_RATE_RPS, MAX_ROOT_YAW_RATE_RPS)

    for offset, (low, high) in enumerate(G1_JOINT_LIMITS_RAD):
        clip(BODY_JOINTS.start + offset, low, high)
    for offset, (low, high) in enumerate(HAND_LIMITS_RAD):
        clip(BODY_DIM + offset, low, high)
        clip(BODY_DIM + HAND_DIM + offset, low, high)

    return projected, worst


PROJECTION_ALARM_RAD = 0.25
"""How far a projection may reach before it stops being fitting error.

A quarter radian is fourteen degrees: far past what a converged regression misses
by, and far short of a joint's full range. Beyond this the policy is commanding
poses this embodiment does not have, which is a training failure rather than a
runtime one.
"""


class LearnedFastPolicy:
    """A trained checkpoint, wearing the ``FastPolicy`` protocol.

    This is the object that occupies the same seam ``ReplayFastPolicy`` occupies,
    which is the point: the actuation path was proven with a replay producer, so
    swapping in learned weights changes the source of the numbers and nothing
    else about the guarantees around them.

    Its output passes through ``WholeBodyTarget`` construction, so a network that
    emits an unexecutable pose produces a clamp record or a refusal -- never an
    unexecutable frame on the wire.
    """

    def __init__(
        self,
        network: object,
        *,
        horizon: int,
        state_normalizer: Normalizer,
        action_normalizer: Normalizer,
        encoder: Optional[ImageEncoder] = None,
        deployable: bool = False,
        not_deployable_because: str = "",
    ) -> None:
        self._network = network
        self._horizon = horizon
        self._state_normalizer = state_normalizer
        self._action_normalizer = action_normalizer
        self._projected_frames = 0
        self._worst_projection_rad = 0.0
        self._encoder = encoder or ImageEncoder()
        self._deployable = deployable
        self._not_deployable_because = not_deployable_because
        self._clamped_frames = 0

    @classmethod
    def load(cls, directory: Path, config: Optional[TrainingConfig] = None):
        torch = _require_torch()
        directory = Path(directory)
        manifest = json.loads((directory / MANIFEST_FILE).read_text())
        payload = manifest["config"]
        config = config or TrainingConfig(
            horizon=int(payload["horizon"]),
            hidden=int(payload["hidden"]),
            layers=int(payload["layers"]),
            epochs=int(payload["epochs"]),
            batch_size=int(payload["batch_size"]),
            learning_rate=float(payload["learning_rate"]),
            weight_decay=float(payload["weight_decay"]),
            validation_fraction=float(payload["validation_fraction"]),
            seed=int(payload["seed"]),
        )
        network = build_network(
            int(manifest["observation_dim"]), int(manifest["output_dim"]), config
        )
        network.load_state_dict(
            torch.load(
                directory / CHECKPOINT_FILE,
                map_location="cpu",
                # A checkpoint is data, not code. Unpickling arbitrary objects
                # from a file that will drive a robot is a needless capability.
                weights_only=True,
            )
        )
        network.eval()
        return cls(
            network,
            horizon=int(manifest["horizon"]),
            state_normalizer=Normalizer.from_payload(manifest["state_normalizer"]),
            action_normalizer=Normalizer.from_payload(
                manifest["action_normalizer"]
            ),
            encoder=_encoder_from_spec(
                manifest.get("image_encoder_spec"),
                int(manifest.get("image_feature_dim", 0)),
            ),
            deployable=bool(manifest.get("deployable", False)),
            not_deployable_because=str(manifest.get("not_deployable_because", "")),
        )

    @property
    def deployable(self) -> tuple[bool, str]:
        return self._deployable, self._not_deployable_because

    @property
    def horizon(self) -> int:
        return self._horizon

    @property
    def projected_frames(self) -> int:
        """How many emitted frames had to be projected onto the executable set."""
        return self._projected_frames

    @property
    def worst_projection_rad(self) -> float:
        """The largest distance any channel was moved to become executable.

        Read this before trusting a policy. Below a few hundredths it is ordinary
        regression error; above ``PROJECTION_ALARM_RAD`` the policy has learned to
        command poses this robot does not have, and no amount of validation loss
        makes that safe.
        """
        return self._worst_projection_rad

    @property
    def projection_alarming(self) -> bool:
        return self._worst_projection_rad > PROJECTION_ALARM_RAD

    @property
    def clamped_frames(self) -> int:
        """How many emitted frames pressed against a contract bound.

        Worth watching rather than logging: a policy whose every frame is clamped
        has learned to command something this embodiment cannot do, and the loss
        curve will not say so.
        """
        return self._clamped_frames

    def act(
        self,
        observation: Observation,
        intent: Optional[SlowIntent],
        first_tick: int,
    ) -> ActionChunk:
        torch = _require_torch()

        row = self._state_normalizer.normalize(
            _flatten_state(observation.state)
        ) + self._encoder.encode(observation.images)
        with torch.no_grad():
            output = self._network(
                torch.tensor([row], dtype=torch.float32)
            )[0].tolist()

        period_ns = int(CONTROL_PERIOD_S * 1e9)
        frames: list[WholeBodyTarget] = []
        for offset in range(self._horizon):
            chunk = output[offset * ACTION_DIM : (offset + 1) * ACTION_DIM]
            if len(chunk) < ACTION_DIM:
                break
            values, excess = project_onto_executable(
                self._action_normalizer.denormalize(chunk)
            )
            if excess > 0.0:
                self._projected_frames += 1
                self._worst_projection_rad = max(
                    self._worst_projection_rad, excess
                )
            frame = WholeBodyTarget(
                sequence=first_tick + offset,
                source_time_ns=observation.time_ns + offset * period_ns,
                valid_until_ns=observation.time_ns + (offset + 3) * period_ns,
                body=tuple(values[:BODY_DIM]),
                left_hand=tuple(values[BODY_DIM : BODY_DIM + HAND_DIM]),
                right_hand=tuple(values[BODY_DIM + HAND_DIM :]),
            )
            if frame.saturated:
                self._clamped_frames += 1
            frames.append(frame)
        return ActionChunk(first_tick=first_tick, frames=tuple(frames))
