"""The Whole-Body Target Contract: the only thing a policy may publish.

One value type, one shape, one clock. Everything upstream -- a learned policy,
a teleoperator, a replay of a recorded episode -- reaches the robot by
constructing a ``WholeBodyTarget`` and handing it to the target bridge. There
is no second path, no partial update, and no field that means "leave the last
value alone".

The layout is not a choice made here. It is what the vendored TWIST2 tracker
on this machine actually consumes, established by reading its real deployment
path rather than its documentation:

``body[35]``        root ``v_x, v_y``, root height ``z``, root ``roll, pitch``,
                    root yaw *rate*, then 29 joint references in G1 order
``left_hand[6]``    ``thumb, thumb_aux, index, middle, ring, pinky``
``right_hand[6]``   the same six, right hand

Four refusals shape this module:

- It refuses partial targets. A frame carries the complete actuation set or it
  is not a frame. A contract with optional fields would make "the hands did not
  update" and "the hands were commanded to hold" the same wire state, and only
  one of those is safe.
- It refuses to carry position. There is no ``x``, no ``y``, no yaw angle, no
  map frame, no waypoint. The root fields are a *local kinodynamic intent*, so
  no reader can mistake this contract for a route and integrate it into a
  position it then trusts.
- It refuses out-of-range values at construction. Joint bounds come from the
  vendored G1 MuJoCo model and hand bounds from the vendored BrainCo wrapper,
  so a target that cannot be executed cannot be built, let alone published.
- It refuses to be its own clock. ``sequence``, ``source_time_ns`` and
  ``valid_until_ns`` are mandatory, because the bridge's freshness and ordering
  rules have nothing to check without them, and the vendored path has neither.

The neck is absent on purpose. Two neck values are produced and recorded by the
vendored teleoperation path, and the vendored tracker JSON-decodes them and
then never uses them: no wrapper, no transport, no feedback. A dormant channel
in this contract would read as a commanded actuator, so it is excluded until it
is commissioned as a verified one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

BODY_DIM = 35
HAND_DIM = 6
JOINT_DIM = 29

CONTROL_PERIOD_S = 0.02
"""The vendored real-robot control period: 50 Hz."""

CONTROL_HZ = 50.0

ROOT_LINEAR_VELOCITY = slice(0, 2)
ROOT_HEIGHT = 2
ROOT_ATTITUDE = slice(3, 5)
ROOT_YAW_RATE = 5
_JOINT_BASE = 6
BODY_JOINTS = slice(_JOINT_BASE, 35)

G1_JOINT_NAMES = (
    "left_hip_pitch_joint",
    "left_hip_roll_joint",
    "left_hip_yaw_joint",
    "left_knee_joint",
    "left_ankle_pitch_joint",
    "left_ankle_roll_joint",
    "right_hip_pitch_joint",
    "right_hip_roll_joint",
    "right_hip_yaw_joint",
    "right_knee_joint",
    "right_ankle_pitch_joint",
    "right_ankle_roll_joint",
    "waist_yaw_joint",
    "waist_roll_joint",
    "waist_pitch_joint",
    "left_shoulder_pitch_joint",
    "left_shoulder_roll_joint",
    "left_shoulder_yaw_joint",
    "left_elbow_joint",
    "left_wrist_roll_joint",
    "left_wrist_pitch_joint",
    "left_wrist_yaw_joint",
    "right_shoulder_pitch_joint",
    "right_shoulder_roll_joint",
    "right_shoulder_yaw_joint",
    "right_elbow_joint",
    "right_wrist_roll_joint",
    "right_wrist_pitch_joint",
    "right_wrist_yaw_joint",
)

G1_JOINT_LIMITS_RAD = (
    (-2.5307, 2.8798),
    (-0.5236, 2.9671),
    (-2.7576, 2.7576),
    (-0.087267, 2.8798),
    (-0.87267, 0.5236),
    (-0.2618, 0.2618),
    (-2.5307, 2.8798),
    (-2.9671, 0.5236),
    (-2.7576, 2.7576),
    (-0.087267, 2.8798),
    (-0.87267, 0.5236),
    (-0.2618, 0.2618),
    (-2.618, 2.618),
    (-0.52, 0.52),
    (-0.52, 0.52),
    (-3.0892, 2.6704),
    (-1.5882, 2.2515),
    (-2.618, 2.618),
    (-1.0472, 2.0944),
    (-1.97222, 1.97222),
    (-1.61443, 1.61443),
    (-1.61443, 1.61443),
    (-3.0892, 2.6704),
    (-2.2515, 1.5882),
    (-2.618, 2.618),
    (-1.0472, 2.0944),
    (-1.97222, 1.97222),
    (-1.61443, 1.61443),
    (-1.61443, 1.61443),
)
"""Read from the vendored ``g1_29dof_rev_1_0.xml``, in tracker joint order."""

HAND_JOINT_NAMES = ("thumb", "thumb_aux", "index", "middle", "ring", "pinky")

HAND_LIMITS_RAD = (
    (0.0, 1.52),
    (0.0, 1.05),
    (0.0, 1.47),
    (0.0, 1.47),
    (0.0, 1.47),
    (0.0, 1.47),
)
"""Read from the vendored BrainCo Revo2 wrapper. Both hands share these."""

HAND_OPEN = (0.0,) * HAND_DIM
HAND_CLOSED = tuple(high for _, high in HAND_LIMITS_RAD)

STAND_BODY: tuple[float, ...] = (
    0.0, 0.0,
    0.8,
    0.0, 0.0,
    0.0,
    -0.2, 0.0, 0.0, 0.4, -0.2, 0.0,
    -0.2, 0.0, 0.0, 0.4, -0.2, 0.0,
    0.0, 0.0, 0.0,
    0.0, 0.4, 0.0, 1.2, 0.0, 0.0, 0.0,
    0.0, -0.4, 0.0, 1.2, 0.0, 0.0, 0.0,
)
"""The vendored default whole-body target: stand still, nominal height, level.

This is ``DEFAULT_MIMIC_OBS_G1`` from the vendored TWIST2 parameters, copied
here rather than imported because the safe-hold path may not depend on a
checkout being present. Its safety does not depend on what the robot was doing
a moment ago, which is the property that makes it usable as a hold.
"""

MAX_ROOT_SPEED_MPS = 0.8
MAX_ROOT_YAW_RATE_RPS = 1.5
ROOT_HEIGHT_RANGE_M = (0.45, 0.95)
MAX_ROOT_TILT_RAD = 0.35
"""Bounds on the root intent, measured against real teleoperation rather than
chosen.

The vendored tracker imposes none of these: it will faithfully attempt any root
velocity a producer writes. An unbounded root channel is the one field where a
single bad frame walks a standing biped into an instrument, so a ceiling has to
exist. Where it sits was taken from the six recorded episodes on this
embodiment (10,531 frames):

===========  =======  =======  ===================
channel      p99.9    max      this ceiling clamps
===========  =======  =======  ===================
speed        0.66     1.03     0.03% of frames
yaw rate     1.30     1.89     0.05% of frames
height       --       0.896    nothing
===========  =======  =======  ===================

The height range is deliberately wider than any recorded frame: every episode
so far is a standing record, and this loop has to bend to reach a bench.
"""

JOINT_SATURATION_MARGIN_RAD = 0.05
"""How far outside its limit a position reference may be saturated rather than
refused.

About 3 degrees: an order of magnitude above this tracker's measured joint error
and fourteen orders above float round-trip noise, so nothing lands here by
accident from either direction.
"""

_NOISE_FLOOR_RAD = 1e-6
"""Below this, a saturation is not worth recording.

A clamp record exists so a human can see the policy pressing against a limit. A
line reading ``-0.087267->-0.087267`` is noise in that record, and a record full
of noise is one nobody reads.
"""

ROOT_SATURATED = "root_saturated"


def _saturate(value: float, low: float, high: float) -> tuple[float, bool]:
    if value < low:
        return low, True
    if value > high:
        return high, True
    return value, False


def _finite(values: Sequence[float], label: str, dim: int) -> tuple[float, ...]:
    if len(values) != dim:
        raise ValueError(f"{label} must carry {dim} values, got {len(values)}")
    out = []
    for index, raw in enumerate(values):
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{label}[{index}] is not a number: {raw!r}"
            ) from exc
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"{label}[{index}] is not finite: {value!r}")
        out.append(value)
    return tuple(out)


def _bounded(
    values: tuple[float, ...],
    limits: Sequence[tuple[float, float]],
    label: str,
    names: Sequence[str],
    margin: float,
) -> tuple[tuple[float, ...], list[str]]:
    """Saturate a position reference to its executable range, or refuse it.

    Two different things arrive here wearing the same shape, and treating them
    identically is wrong either way.

    A reference a hair outside its limit is *numerical*. The vendored
    retargeter already clamps to the joint limit, and a JSON round trip perturbs
    the last bit, so recorded frames carry knee references of
    ``-0.08726700000000001`` against a limit of ``-0.087267``. That difference
    is fourteen orders of magnitude below this robot's tracking error. Refusing
    it would reject a quarter of every real teleoperation episode over the
    representation of a number.

    A reference far outside its limit is *authorship*. A knee at 9 rad is a
    frame someone computed wrongly, and saturating it silently would hand the
    tracker a pose nobody intended while reporting success.

    So the margin is the line between them: inside it, saturate and record;
    outside it, refuse. The margin is set well below the tracker's own accuracy
    and well above float noise, which leaves a wide gap where neither reading is
    plausible.
    """
    mutable = list(values)
    clamped: list[str] = []
    for index, (value, (low, high)) in enumerate(zip(values, limits)):
        if low <= value <= high:
            continue
        edge = low if value < low else high
        excess = abs(value - edge)
        if excess > margin:
            raise ValueError(
                f"{label}[{index}] ({names[index]}) is {value}, outside the "
                f"executable range [{low}, {high}] by {excess:.4f} rad -- "
                f"beyond the {margin} rad saturation margin, so this is an "
                f"authoring error rather than numerical noise"
            )
        mutable[index] = edge
        if excess > _NOISE_FLOOR_RAD:
            clamped.append(
                f"{label}[{index}] {names[index]} {value:.4f}->{edge:.4f} rad"
            )
    return tuple(mutable), clamped


@dataclass(frozen=True)
class WholeBodyTarget:
    """One complete, ordered, expiring actuation frame.

    Construction is the validation. A ``WholeBodyTarget`` that exists is one
    the tracker and both hands can execute, which is why every other component
    in this package accepts the type rather than three arrays.
    """

    sequence: int
    source_time_ns: int
    valid_until_ns: int
    body: tuple[float, ...]
    left_hand: tuple[float, ...]
    right_hand: tuple[float, ...]
    clamped: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("sequence must be non-negative")
        if self.source_time_ns <= 0:
            raise ValueError("source_time_ns must be a positive timestamp")
        if self.valid_until_ns <= self.source_time_ns:
            raise ValueError(
                "valid_until_ns must be after source_time_ns; a frame that "
                "expires on arrival can never be published"
            )

        body = _finite(self.body, "body", BODY_DIM)
        left = _finite(self.left_hand, "left_hand", HAND_DIM)
        right = _finite(self.right_hand, "right_hand", HAND_DIM)

        mutable = list(body)
        clamped: list[str] = []

        speed = (body[0] ** 2 + body[1] ** 2) ** 0.5
        if speed > MAX_ROOT_SPEED_MPS:
            scale = MAX_ROOT_SPEED_MPS / speed
            mutable[0] = body[0] * scale
            mutable[1] = body[1] * scale
            clamped.append(f"speed {speed:.3f}->{MAX_ROOT_SPEED_MPS} m/s")

        low, high = ROOT_HEIGHT_RANGE_M
        mutable[ROOT_HEIGHT], hit = _saturate(body[ROOT_HEIGHT], low, high)
        if hit:
            clamped.append(f"height {body[ROOT_HEIGHT]:.3f}->{mutable[ROOT_HEIGHT]:.3f} m")

        for index, axis in ((3, "roll"), (4, "pitch")):
            mutable[index], hit = _saturate(
                body[index], -MAX_ROOT_TILT_RAD, MAX_ROOT_TILT_RAD
            )
            if hit:
                clamped.append(
                    f"{axis} {body[index]:.3f}->{mutable[index]:.3f} rad"
                )

        mutable[ROOT_YAW_RATE], hit = _saturate(
            body[ROOT_YAW_RATE], -MAX_ROOT_YAW_RATE_RPS, MAX_ROOT_YAW_RATE_RPS
        )
        if hit:
            clamped.append(
                f"yaw rate {body[ROOT_YAW_RATE]:.3f}->"
                f"{mutable[ROOT_YAW_RATE]:.3f} rad/s"
            )

        body = tuple(mutable)

        joints, joint_clamped = _bounded(
            body[BODY_JOINTS],
            G1_JOINT_LIMITS_RAD,
            "body joint",
            G1_JOINT_NAMES,
            JOINT_SATURATION_MARGIN_RAD,
        )
        body = body[:_JOINT_BASE] + joints
        clamped.extend(joint_clamped)

        left, left_clamped = _bounded(
            left, HAND_LIMITS_RAD, "left_hand", HAND_JOINT_NAMES,
            JOINT_SATURATION_MARGIN_RAD,
        )
        clamped.extend(left_clamped)
        right, right_clamped = _bounded(
            right, HAND_LIMITS_RAD, "right_hand", HAND_JOINT_NAMES,
            JOINT_SATURATION_MARGIN_RAD,
        )
        clamped.extend(right_clamped)

        object.__setattr__(self, "body", body)
        object.__setattr__(self, "left_hand", left)
        object.__setattr__(self, "right_hand", right)
        object.__setattr__(self, "clamped", tuple(clamped))

    @property
    def saturated(self) -> bool:
        """Whether any root channel was clamped on the way in.

        Reported rather than raised. Root velocity is a finite difference of a
        human demonstrator's motion, so isolated frames overshoot any ceiling by
        differentiation noise alone -- in the six recorded episodes the longest
        run above 0.8 m/s is a single 20 ms frame. Refusing those frames would
        end an episode over noise, and silently clamping them would hide a
        producer genuinely trying to run away. So the frame is clamped, the
        clamp is recorded, and *sustained* saturation is what the bridge treats
        as a fault.
        """
        return bool(self.clamped)

    @property
    def root_velocity_mps(self) -> tuple[float, float]:
        return (self.body[0], self.body[1])

    @property
    def joints_rad(self) -> tuple[float, ...]:
        return self.body[BODY_JOINTS]

    def expired_at(self, now_ns: int) -> bool:
        return now_ns >= self.valid_until_ns

    def is_stationary(self) -> bool:
        """Whether this frame commands no root motion at all."""
        return (
            self.body[0] == 0.0
            and self.body[1] == 0.0
            and self.body[ROOT_YAW_RATE] == 0.0
        )

    def as_payload(self) -> Mapping[str, object]:
        """The frame as plain data, for a wire, a ledger, or a record."""
        return {
            "sequence": self.sequence,
            "source_time_ns": self.source_time_ns,
            "valid_until_ns": self.valid_until_ns,
            "body": list(self.body),
            "left_hand": list(self.left_hand),
            "right_hand": list(self.right_hand),
            "clamped": list(self.clamped),
        }


def safe_hold_target(
    sequence: int,
    now_ns: int,
    left_hand: Sequence[float] = HAND_OPEN,
    right_hand: Sequence[float] = HAND_OPEN,
    hold_periods: int = 5,
) -> WholeBodyTarget:
    """The Safe Hold Target: what a lapse of authority resolves to.

    Per-actuator, because the safe direction differs between them. The body
    gets the vendored stand target, whose safety does not depend on what the
    robot was doing. The hands keep their last commanded aperture, because
    releasing a held vessel is irreversible and holding it is not.

    It is a published target with its own expiry, not an omission and not a
    deletion. On this embodiment the tracker is what keeps a standing biped
    upright, so withholding a frame does not stop the robot -- it stops the
    thing that was balancing it.
    """
    if hold_periods < 1:
        raise ValueError("a safe hold must be valid for at least one period")
    span_ns = int(hold_periods * CONTROL_PERIOD_S * 1e9)
    return WholeBodyTarget(
        sequence=sequence,
        source_time_ns=now_ns,
        valid_until_ns=now_ns + span_ns,
        body=STAND_BODY,
        left_hand=tuple(left_hand),
        right_hand=tuple(right_hand),
    )
