"""The retargeting layer: a checkpoint's numbers become this robot's joints.

``embodiment`` can prove that a checkpoint and a robot disagree. It cannot
convert between them, and until something does, a policy's output is a
23-vector nobody can execute. This module is that conversion, and it exists as
its own module because it is the one part of the VLA path whose correctness is
neither a dimension check nor a physical measurement: every layer here can
produce numbers that are the right shape, the right magnitude, and the wrong
motion.

The published ``UnifoLM-VLA-Base`` action vector is three unrelated encodings
concatenated, and each one is a place to be silently wrong:

``0:3``    left end-effector position, metres, pelvis frame
``3:9``    left end-effector rotation, 6D -- the first two *columns* of R
``9:12``   right end-effector position
``12:18``  right end-effector rotation, 6D
``18:20``  gripper apertures, 0 to 4.5, Dex1-1 semantics
``20:23``  waist

Every one of those facts was measured against the checkpoint's own statistics
and the published ``G1_Dex1_Stack_Block`` recordings rather than read from a
document, because the documents disagree with the weights: the checkpoint's
``config.yaml`` declares ``action_dim: 7``, a leftover from a LIBERO template.

Three refusals:

- It refuses to guess the 6D convention. Columns and rows are the same six
  numbers in a different order, both are unit-norm, and both pass every check
  a shape can express -- while producing wrist orientations that differ by tens
  of degrees. The convention is therefore pinned by a fingerprint that
  distinguishes them: on the published recordings, the column reading puts
  100% of frames inside the checkpoint's own action envelope and the row
  reading puts 9-16% inside it.
- It refuses to invent the tool frame. The recordings' end-effector poses sit
  a fixed 50.0 mm along the wrist's own x-axis with zero relative rotation --
  solved to 0.3 mm and 0.1 degrees on both arms, which is a mechanical
  constant, not a fit. A layer that omitted it would command every pose 5 cm
  short, consistently, which reads as a policy that keeps missing.
- It refuses to pretend a 6-DOF target determines 7 joints. A redundant arm
  reaches the same pose along a one-parameter family, so the resolved joints
  are *a* solution and the module says so. Which one to pick is a policy
  decision, and the seed pose is how a caller expresses it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

ACTION_DIM = 23

SLICE_LEFT_POSITION = slice(0, 3)
SLICE_LEFT_ROTATION = slice(3, 9)
SLICE_RIGHT_POSITION = slice(9, 12)
SLICE_RIGHT_ROTATION = slice(12, 18)
SLICE_GRIPPERS = slice(18, 20)
SLICE_WAIST = slice(20, 23)

ROTATION_6D_COLUMNS = "columns"
"""The published checkpoint's 6D layout: R[:, 0] followed by R[:, 1].

Named rather than assumed. See the module docstring for the measurement that
distinguishes it from the row layout; the two are indistinguishable by shape.
"""

ROTATION_6D_ROWS = "rows"
"""The other layout: R[0, :] followed by R[1, :].

Named only so that it can be *asked for* deliberately, and so that a caller
comparing the two has a word for the one the measurement rejected. On the
published recordings this reading differs from the column reading by 109
degrees on average, so selecting it by accident is not a small error.
"""

ROTATION_6D_LAYOUTS = (ROTATION_6D_COLUMNS, ROTATION_6D_ROWS)


def _require_layout(layout: str) -> str:
    """Reject a layout nobody defined, instead of falling through to rows.

    This function exists because of the shape of the bug it prevents. With an
    ``if columns / else rows`` branch, every typo, every stale constant, and
    every ``None`` becomes a silent request for the row layout -- which is
    wrong by tens of degrees while remaining six unit-norm numbers that pass
    every check a shape or a magnitude can express. An unknown layout is a
    caller error and has to be said out loud.
    """
    if layout not in ROTATION_6D_LAYOUTS:
        raise ValueError(
            f"unknown 6D rotation layout {layout!r}; expected one of "
            f"{list(ROTATION_6D_LAYOUTS)!r}. Guessing would silently select "
            "the row reading, which the published recordings reject"
        )
    return layout

TOOL_OFFSET_M = (0.05002, 0.0, 0.0)
"""Where the recorded end-effector sits in the wrist-yaw frame.

Solved from the published recordings on both arms independently and agreeing to
20 microns. Declared as a constant because it is a property of the gripper that
was bolted on when the data was recorded, and a laboratory with a different
tool must measure its own.
"""

GRIPPER_RANGE = (0.0, 4.5)
"""The aperture range the checkpoint's statistics span, in its own units.

Not metres and not radians: an opaque actuator scale. Converting it to another
hand's command is a separate claim this module refuses to make.
"""


def rotation_from_6d(
    values: Sequence[float], layout: str = ROTATION_6D_COLUMNS
) -> np.ndarray:
    """Rebuild a rotation matrix from its 6D encoding.

    Gram-Schmidt rather than a reshape: the six numbers a policy emits are not
    guaranteed orthonormal, and a matrix that is merely close to a rotation
    will compose into a pose that drifts. Orthonormalising here means every
    downstream stage receives an actual rotation.
    """
    _require_layout(layout)
    raw = np.asarray(values, dtype=float).reshape(6)
    a, b = raw[:3], raw[3:]
    norm = np.linalg.norm(a)
    if norm < 1e-9:
        raise ValueError(
            "the first 6D triple has no length, so it defines no direction; "
            "this is a malformed action rather than an unusual pose"
        )
    e0 = a / norm
    projected = b - float(e0 @ b) * e0
    norm = np.linalg.norm(projected)
    if norm < 1e-9:
        raise ValueError(
            "the two 6D triples are parallel, so they span no plane and "
            "cannot define an orientation"
        )
    e1 = projected / norm
    e2 = np.cross(e0, e1)
    if layout == ROTATION_6D_COLUMNS:
        return np.stack([e0, e1, e2], axis=1)
    return np.stack([e0, e1, e2], axis=0)


def rotation_to_6d(
    matrix: np.ndarray, layout: str = ROTATION_6D_COLUMNS
) -> np.ndarray:
    """The inverse encoding, for building an observation the policy expects."""
    _require_layout(layout)
    m = np.asarray(matrix, dtype=float).reshape(3, 3)
    if layout == ROTATION_6D_COLUMNS:
        return np.concatenate([m[:, 0], m[:, 1]])
    return np.concatenate([m[0, :], m[1, :]])


@dataclass(frozen=True)
class EndEffectorPose:
    """One arm's commanded pose, in the frame the checkpoint speaks."""

    position_m: tuple[float, float, float]
    rotation: tuple[tuple[float, ...], ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "position_m", tuple(float(v) for v in self.position_m)
        )
        object.__setattr__(
            self,
            "rotation",
            tuple(tuple(float(v) for v in row) for row in self.rotation),
        )
        if len(self.position_m) != 3:
            raise ValueError("a position needs three components")
        if len(self.rotation) != 3 or any(
            len(row) != 3 for row in self.rotation
        ):
            raise ValueError("a rotation needs to be three by three")

    @property
    def matrix(self) -> np.ndarray:
        return np.asarray(self.rotation, dtype=float)

    def with_tool_offset(
        self, offset_m: Sequence[float] = TOOL_OFFSET_M
    ) -> "EndEffectorPose":
        """The wrist pose that puts *this* tool pose where it was asked for.

        The offset is expressed in the wrist's own frame, so it rotates with
        the wrist. Subtracting it in the world frame instead would be correct
        at exactly one orientation and wrong at every other, which is the kind
        of error that looks like a policy with a systematic bias.
        """
        matrix = self.matrix
        shift = matrix @ np.asarray(offset_m, dtype=float)
        return EndEffectorPose(
            position_m=tuple(np.asarray(self.position_m) - shift),
            rotation=self.rotation,
        )


@dataclass(frozen=True)
class PolicyAction:
    """One decoded 23-vector, as the things it actually contains."""

    left: EndEffectorPose
    right: EndEffectorPose
    gripper_apertures: tuple[float, float]
    waist: tuple[float, float, float]

    @classmethod
    def decode(
        cls, action: Sequence[float], layout: str = ROTATION_6D_COLUMNS
    ) -> "PolicyAction":
        """Split a raw action vector into its three unrelated encodings."""
        values = np.asarray(action, dtype=float).reshape(-1)
        if values.size != ACTION_DIM:
            raise ValueError(
                f"expected {ACTION_DIM} action dimensions, got {values.size}; "
                "the published UnifoLM-VLA-Base G1 contract is 23, and a "
                "16-dimensional vector means the upstream loader selected "
                "joint-mode constants from launch-command text"
            )
        return cls(
            left=EndEffectorPose(
                position_m=tuple(values[SLICE_LEFT_POSITION]),
                rotation=tuple(
                    tuple(row)
                    for row in rotation_from_6d(
                        values[SLICE_LEFT_ROTATION], layout
                    )
                ),
            ),
            right=EndEffectorPose(
                position_m=tuple(values[SLICE_RIGHT_POSITION]),
                rotation=tuple(
                    tuple(row)
                    for row in rotation_from_6d(
                        values[SLICE_RIGHT_ROTATION], layout
                    )
                ),
            ),
            gripper_apertures=(
                float(values[SLICE_GRIPPERS][0]),
                float(values[SLICE_GRIPPERS][1]),
            ),
            waist=tuple(float(v) for v in values[SLICE_WAIST]),
        )


def denormalize(
    normalized: Sequence[float],
    minimum: Sequence[float],
    maximum: Sequence[float],
    mask: Optional[Sequence[bool]] = None,
) -> np.ndarray:
    """Undo the checkpoint's bounds normalization.

    ``bounds_q99`` maps each dimension's first-to-ninety-ninth percentile onto
    [-1, 1], so the inverse is an affine map back. ``mask`` marks dimensions
    the statistics say were never normalized; passing them through the affine
    map anyway is the classic silent scaling error, so they are copied
    verbatim.
    """
    values = np.asarray(normalized, dtype=float).reshape(-1)
    lo = np.asarray(minimum, dtype=float).reshape(-1)
    hi = np.asarray(maximum, dtype=float).reshape(-1)
    if not (values.size == lo.size == hi.size):
        raise ValueError(
            f"action has {values.size} dimensions but the statistics describe "
            f"{lo.size}; a mismatch here silently rescales every command"
        )
    out = 0.5 * (values + 1.0) * (hi - lo) + lo
    if mask is not None:
        flags = np.asarray(mask, dtype=bool).reshape(-1)
        if flags.size != values.size:
            raise ValueError("the normalization mask has the wrong width")
        out = np.where(flags, out, values)
    return out


@dataclass(frozen=True)
class RetargetResult:
    """Joints that reach a commanded pose, and how well they reach it.

    The errors are reported rather than thresholded because this module cannot
    know what a caller's tolerance is. What it can guarantee is that a caller
    who ignores them is choosing to.
    """

    joint_positions_rad: tuple[float, ...]
    position_error_m: float
    rotation_error_rad: float
    iterations: int
    converged: bool
    detail: str = ""


class ArmRetargeter:
    """Resolves a commanded end-effector pose into one arm's joint angles.

    Damped least squares on the arm's own Jacobian, iterated from a seed pose.
    The choice of method matters less than three properties it was chosen for:
    it needs no analytic inverse for a 7-joint chain, it stays well-behaved at
    the singularities a redundant arm passes through, and it is warm-startable,
    so consecutive waypoints in an action chunk resolve to a continuous joint
    path instead of jumping between null-space branches.

    That last property is why the seed is a parameter and not an internal
    detail. A 6-DOF pose leaves one DOF of a 7-joint arm undetermined, so the
    seed is what selects a solution from a one-parameter family. Solving each
    waypoint from a fixed home pose would produce poses that are individually
    correct and collectively a series of elbow flips.

    It carries no safety authority. It reports what it reached and how far off
    it is; whether that is close enough, whether the joints are inside limits
    the laboratory permits, and whether the robot may move at all are decided
    above this boundary.
    """

    def __init__(
        self,
        model: object,
        joint_names: Sequence[str],
        wrist_body: str,
        tool_offset_m: Sequence[float] = TOOL_OFFSET_M,
        reference_body: Optional[str] = None,
        damping: float = 1e-3,
        max_iterations: int = 80,
        position_tolerance_m: float = 1e-4,
        rotation_tolerance_rad: float = 1e-3,
    ) -> None:
        import mujoco  # imported here so the module is usable without it

        self._mj = mujoco
        self._model = model
        self._data = mujoco.MjData(model)  # type: ignore[arg-type]
        self._joint_names = tuple(joint_names)
        if not self._joint_names:
            raise ValueError("a retargeter needs at least one joint to solve")

        self._dof_indices: list[int] = []
        self._qpos_indices: list[int] = []
        for name in self._joint_names:
            jid = mujoco.mj_name2id(  # type: ignore[attr-defined]
                model, mujoco.mjtObj.mjOBJ_JOINT, name
            )
            if jid < 0:
                raise ValueError(f"joint {name!r} is not in this model")
            self._dof_indices.append(int(model.jnt_dofadr[jid]))
            self._qpos_indices.append(int(model.jnt_qposadr[jid]))

        self._wrist_id = mujoco.mj_name2id(  # type: ignore[attr-defined]
            model, mujoco.mjtObj.mjOBJ_BODY, wrist_body
        )
        if self._wrist_id < 0:
            raise ValueError(f"body {wrist_body!r} is not in this model")
        self._reference_id = -1
        if reference_body is not None:
            self._reference_id = mujoco.mj_name2id(  # type: ignore[attr-defined]
                model, mujoco.mjtObj.mjOBJ_BODY, reference_body
            )
            if self._reference_id < 0:
                raise ValueError(f"body {reference_body!r} is not in this model")

        self._tool_offset = np.asarray(tool_offset_m, dtype=float)
        self._damping = float(damping)
        self._max_iterations = int(max_iterations)
        self._position_tolerance = float(position_tolerance_m)
        self._rotation_tolerance = float(rotation_tolerance_rad)

    @property
    def joint_names(self) -> tuple[str, ...]:
        return self._joint_names

    def forward(
        self, joint_positions_rad: Sequence[float]
    ) -> EndEffectorPose:
        """Where this joint vector actually puts the tool.

        Exposed because it is the only way a caller can check a retargeting
        result without trusting this class: solve, then run the answer forward
        and compare against what was asked for.
        """
        self._write(joint_positions_rad)
        self._refresh()
        position, matrix = self._tool_pose()
        return EndEffectorPose(
            position_m=tuple(position), rotation=tuple(tuple(r) for r in matrix)
        )

    def solve(
        self,
        target: EndEffectorPose,
        seed_joint_positions_rad: Sequence[float],
    ) -> RetargetResult:
        """Find joints that put the tool at ``target``, starting from the seed."""
        q = np.asarray(seed_joint_positions_rad, dtype=float).copy()
        if q.size != len(self._joint_names):
            raise ValueError(
                f"seed has {q.size} joints but this arm has "
                f"{len(self._joint_names)}"
            )
        target_position = np.asarray(target.position_m, dtype=float)
        target_matrix = target.matrix

        position_error = float("inf")
        rotation_error = float("inf")
        iterations = 0
        for iterations in range(1, self._max_iterations + 1):
            self._write(q)
            self._refresh()
            position, matrix = self._tool_pose()

            position_residual = target_position - position
            rotation_residual = self._rotation_residual(matrix, target_matrix)
            position_error = float(np.linalg.norm(position_residual))
            rotation_error = float(np.linalg.norm(rotation_residual))
            if (
                position_error <= self._position_tolerance
                and rotation_error <= self._rotation_tolerance
            ):
                break

            jacobian = self._tool_jacobian()
            residual = np.concatenate([position_residual, rotation_residual])
            # Damped least squares: the damping is what keeps a near-singular
            # configuration from demanding an enormous joint step, which on
            # hardware is the difference between a slow approach and a snap.
            jjt = jacobian @ jacobian.T
            jjt += (self._damping**2) * np.eye(6)
            step = jacobian.T @ np.linalg.solve(jjt, residual)
            q = self._clamp(q + step)

        converged = (
            position_error <= self._position_tolerance
            and rotation_error <= self._rotation_tolerance
        )
        detail = (
            ""
            if converged
            else (
                f"did not converge in {self._max_iterations} iterations: "
                f"{position_error:.5f} m and {rotation_error:.5f} rad remain. "
                "The pose may be outside this arm's reach, or the seed may be "
                "in a different null-space branch than the target"
            )
        )
        return RetargetResult(
            joint_positions_rad=tuple(float(v) for v in q),
            position_error_m=position_error,
            rotation_error_rad=rotation_error,
            iterations=iterations,
            converged=converged,
            detail=detail,
        )

    def _write(self, joint_positions_rad: Sequence[float]) -> None:
        for index, value in zip(self._qpos_indices, joint_positions_rad):
            self._data.qpos[index] = float(value)

    def _refresh(self) -> None:
        """Recompute everything the pose *and the Jacobian* are read from.

        ``mj_kinematics`` alone is enough to read a body's pose, which is why
        an implementation that only calls it appears to work: forward kinematics
        is exact and every pose check passes. But ``mj_jac`` differentiates
        through the centre-of-mass quantities that ``mj_comPos`` fills in, and
        on fresh data those are zero. The Jacobian is then all zeros, every
        damped-least-squares step is zero, and the solver reports the seed pose
        back after exhausting its iterations -- a failure that looks like an
        unreachable target rather than a missing call.
        """
        self._mj.mj_kinematics(self._model, self._data)
        self._mj.mj_comPos(self._model, self._data)

    def _tool_pose(self) -> tuple[np.ndarray, np.ndarray]:
        wrist_position = np.array(self._data.xpos[self._wrist_id])
        wrist_matrix = np.array(self._data.xmat[self._wrist_id]).reshape(3, 3)
        position = wrist_position + wrist_matrix @ self._tool_offset
        if self._reference_id >= 0:
            reference_position = np.array(self._data.xpos[self._reference_id])
            reference_matrix = np.array(
                self._data.xmat[self._reference_id]
            ).reshape(3, 3)
            position = reference_matrix.T @ (position - reference_position)
            wrist_matrix = reference_matrix.T @ wrist_matrix
        return position, wrist_matrix

    def _tool_jacobian(self) -> np.ndarray:
        jacp = np.zeros((3, self._model.nv))
        jacr = np.zeros((3, self._model.nv))
        wrist_matrix = np.array(self._data.xmat[self._wrist_id]).reshape(3, 3)
        point = np.array(self._data.xpos[self._wrist_id]) + (
            wrist_matrix @ self._tool_offset
        )
        self._mj.mj_jac(
            self._model, self._data, jacp, jacr, point, self._wrist_id
        )
        if self._reference_id >= 0:
            reference_matrix = np.array(
                self._data.xmat[self._reference_id]
            ).reshape(3, 3)
            jacp = reference_matrix.T @ jacp
            jacr = reference_matrix.T @ jacr
        columns = np.asarray(self._dof_indices, dtype=int)
        return np.vstack([jacp[:, columns], jacr[:, columns]])

    def _rotation_residual(
        self, current: np.ndarray, target: np.ndarray
    ) -> np.ndarray:
        relative = current.T @ target
        quaternion = np.zeros(4)
        self._mj.mju_mat2Quat(quaternion, relative.reshape(9))
        velocity = np.zeros(3)
        self._mj.mju_quat2Vel(velocity, quaternion, 1.0)
        return current @ velocity

    def _clamp(self, q: np.ndarray) -> np.ndarray:
        for position, name in enumerate(self._joint_names):
            jid = self._mj.mj_name2id(
                self._model, self._mj.mjtObj.mjOBJ_JOINT, name
            )
            if not self._model.jnt_limited[jid]:
                continue
            low, high = self._model.jnt_range[jid]
            q[position] = min(max(q[position], low), high)
        return q
