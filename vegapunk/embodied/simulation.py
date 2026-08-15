"""A MuJoCo ``RobotInterface`` for the G1, and the frame bus its cameras feed.

This is the first environment that can supply ``offline_replay`` evidence. It
exists because the admission ladder demands evidence before a person stands
next to a moving robot, and until now nothing in the profile could produce any.

What it measures and what it does not is the whole point of the module. Joint
positions, joint velocities, end-effector position, and contact force on the
end effector are computed by the physics engine, so they are measurements in
the only sense simulation can offer. Velocity and force are reported as peaks
over the interval since the last read rather than as the latest sample, because
a position actuator converges within one control period: sample only the period
boundary and a joint that peaked far above the envelope reads as nearly at
rest. Human supervision is not measured: whether a
guardian is present, whether the estop is reachable, and whether the workspace
is clear are facts about a room, and a simulator that invented them would be
manufacturing exactly the preconditions the Safety Supervisor exists to check.
They must therefore be declared by an operator through ``SimulatedSupervision``
and are reported as declared, never as observed.

Four refusals:

- It refuses to be mistaken for hardware. ``is_real_robot`` is false and
  ``SIMULATION_STAGE`` is ``offline_replay``, which the trajectory ledger
  already excludes from real-robot training data. Simulated runs can earn
  admission towards the next stage; they can never become a hardware dataset.
- It refuses to keep commanding after ``hold``. Stopping is latched here as
  well as in the runtime, because a stop that only one layer honours is not a
  stop.
- It refuses to report velocity and force only at control-period boundaries.
  The envelope bounds every instant, so a sampling scheme that can only see
  the quiet moments is not a safety measurement at all.
- It refuses to render from a thread other than the one that built its GL
  context, which is a silent corruption rather than an error in MuJoCo. The
  preview transport therefore reads finished frames from ``FrameBus`` and never
  touches the simulation.
- It refuses unknown or multi-DoF controlled joints. A goal pose is a list of
  numbers whose meaning is entirely positional, so the joint list it indexes
  into has to be exact.

The pelvis is welded to the world. Version 1 governs arm-and-gripper macro
actions, and a free-floating base would add a balance failure mode that has
nothing to do with the skill under test and would abort every run.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Optional, Sequence

import numpy as np

from vegapunk.embodied.admission import STAGE_OFFLINE_REPLAY
from vegapunk.embodied.fidelity import SimulatedConfiguration
from vegapunk.embodied.runtime import RobotState

SIMULATION_STAGE = STAGE_OFFLINE_REPLAY

CAMERA_SLOT_HEAD = "head"
CAMERA_SLOT_LEFT_WRIST = "leftWrist"
CAMERA_SLOT_RIGHT_WRIST = "rightWrist"

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENE_PATH = (
    _REPO_ROOT
    / "third_party"
    / "mujoco_menagerie"
    / "unitree_g1"
    / "scene_with_hands.xml"
)

_SOURCE_WIDTH = 640
_SOURCE_HEIGHT = 480
_STAND_KEYFRAME = "stand"
_FREE_BASE_QPOS = 7
_PELVIS_STAND_HEIGHT_M = 0.793

G1_LEFT_ARM_JOINTS = (
    "left_shoulder_pitch_joint",
    "left_shoulder_roll_joint",
    "left_shoulder_yaw_joint",
    "left_elbow_joint",
    "left_wrist_roll_joint",
    "left_wrist_pitch_joint",
    "left_wrist_yaw_joint",
)

G1_RIGHT_ARM_JOINTS = tuple(
    name.replace("left_", "right_", 1) for name in G1_LEFT_ARM_JOINTS
)


_HEADLESS_GL_BACKEND = "egl"
_DISPLAY_VARIABLES = ("DISPLAY", "WAYLAND_DISPLAY")


def _import_mujoco() -> object:
    """Import MuJoCo with a rendering backend that suits the host.

    MuJoCo binds its GL backend once, at import time, from ``MUJOCO_GL``. Left
    unset it chooses GLFW, which needs a windowing system and calls ``abort()``
    rather than raising when there is none: on a headless host the whole
    process dies with no traceback. A run on a server is the normal case here,
    so when no display is advertised the backend is pinned to EGL, which
    renders offscreen on the GPU. An explicit ``MUJOCO_GL`` is always honoured,
    because a caller who names a backend knows their host better than this
    default does.
    """
    if not os.environ.get("MUJOCO_GL") and not any(
        os.environ.get(name) for name in _DISPLAY_VARIABLES
    ):
        os.environ["MUJOCO_GL"] = _HEADLESS_GL_BACKEND

    import mujoco

    return mujoco


@dataclass(frozen=True)
class CameraSlot:
    """One GUI camera pane and the simulated cameras that fill it.

    ``preview_port`` is not a preference. The GUI hard-codes one fixed port per
    pane, so a slot that does not carry the port it will be served on cannot be
    displayed.
    """

    slot_id: str
    width: int
    height: int
    preview_port: int
    sources: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "sources", tuple(self.sources))
        if not self.sources:
            raise ValueError(f"camera slot {self.slot_id!r} has no sources")
        if self.width != _SOURCE_WIDTH * len(self.sources):
            raise ValueError(
                f"camera slot {self.slot_id!r} declares width {self.width} but "
                f"{len(self.sources)} sources tile to "
                f"{_SOURCE_WIDTH * len(self.sources)}"
            )


CAMERA_SLOTS: Mapping[str, CameraSlot] = MappingProxyType(
    {
        CAMERA_SLOT_HEAD: CameraSlot(
            slot_id=CAMERA_SLOT_HEAD,
            width=_SOURCE_WIDTH * 2,
            height=_SOURCE_HEIGHT,
            preview_port=60001,
            sources=("head_left", "head_right"),
        ),
        CAMERA_SLOT_LEFT_WRIST: CameraSlot(
            slot_id=CAMERA_SLOT_LEFT_WRIST,
            width=_SOURCE_WIDTH,
            height=_SOURCE_HEIGHT,
            preview_port=60002,
            sources=("left_wrist",),
        ),
        CAMERA_SLOT_RIGHT_WRIST: CameraSlot(
            slot_id=CAMERA_SLOT_RIGHT_WRIST,
            width=_SOURCE_WIDTH,
            height=_SOURCE_HEIGHT,
            preview_port=60003,
            sources=("right_wrist",),
        ),
    }
)


class FrameBus:
    """The only thing the preview transport is allowed to read.

    MuJoCo's renderer belongs to the thread that created its GL context, so the
    simulation publishes finished RGB frames here and the transport reads the
    most recent one. A slow or absent consumer drops frames instead of stalling
    the control loop, which is the correct priority: the run matters, the
    picture of it does not.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frames: dict[str, np.ndarray] = {}
        self._counts: dict[str, int] = {}

    def publish(self, slot_id: str, frame: np.ndarray) -> None:
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError(
                f"frame for {slot_id!r} is not an (H, W, 3) RGB array: "
                f"{frame.shape}"
            )
        if frame.dtype != np.uint8:
            raise ValueError(
                f"frame for {slot_id!r} must be uint8, got {frame.dtype}"
            )
        with self._lock:
            self._frames[slot_id] = frame
            self._counts[slot_id] = self._counts.get(slot_id, 0) + 1

    def latest(self, slot_id: str) -> Optional[np.ndarray]:
        with self._lock:
            return self._frames.get(slot_id)

    def frame_count(self, slot_id: str) -> int:
        with self._lock:
            return self._counts.get(slot_id, 0)


@dataclass(frozen=True)
class SimulatedSupervision:
    """The room facts a simulation cannot measure and must be told.

    No field has a default. Every one of them is a precondition the supervisor
    checks before allowing motion, and a default here would silently satisfy a
    safety check on behalf of a human who was never asked.
    """

    guardian_present: bool
    estop_engaged: bool
    estop_reachable: bool
    workspace_clear: bool


class SimulatedG1:
    """A welded-base G1 in MuJoCo, presented as a ``RobotInterface``.

    One instance owns one MuJoCo model, one data buffer, and one renderer, all
    bound to the constructing thread. ``controlled_joints`` fixes the meaning of
    every joint vector this interface accepts or reports; joints outside that
    list are held at the standing keyframe.
    """

    def __init__(
        self,
        controlled_joints: Sequence[str] = G1_LEFT_ARM_JOINTS,
        supervision: Optional[SimulatedSupervision] = None,
        control_frequency_hz: float = 50.0,
        end_effector_body: str = "left_wrist_yaw_link",
        end_effector_offset_m: Sequence[float] = (0.115, 0.003, 0.0),
        scene_path: Path = DEFAULT_SCENE_PATH,
        observation_age_s: Optional[float] = None,
    ) -> None:
        if control_frequency_hz <= 0:
            raise ValueError("control_frequency_hz must be positive")
        if supervision is None:
            raise ValueError(
                "a simulated run must declare its supervision facts; a "
                "simulator that assumes a guardian is present has "
                "manufactured the precondition the supervisor exists to check"
            )
        if not controlled_joints:
            raise ValueError("controlled_joints cannot be empty")

        mujoco = _import_mujoco()

        self._mujoco = mujoco
        self._scene_path = Path(scene_path)
        if not self._scene_path.exists():
            raise FileNotFoundError(
                f"MJCF scene not found at {self._scene_path}; the G1 model "
                "comes from mujoco_menagerie and is not vendored in this "
                "repository"
            )

        self._owner_thread = threading.get_ident()
        self._model = self._build_model(
            end_effector_body, tuple(float(v) for v in end_effector_offset_m)
        )
        self._data = mujoco.MjData(self._model)

        self._joint_names = tuple(controlled_joints)
        self._qpos_index = self._resolve_qpos_index(self._joint_names)
        self._dof_index = self._resolve_dof_index(self._joint_names)
        self._ctrl_index = self._resolve_ctrl_index(self._joint_names)

        self._joint_range = self._resolve_joint_range(self._joint_names)
        self._end_effector_site_id = self._model.site("end_effector").id
        self._end_effector_geoms = self._subtree_geoms(end_effector_body)

        self._control_frequency_hz = float(control_frequency_hz)
        self._control_period_s = 1.0 / self._control_frequency_hz
        steps = round(self._control_period_s / self._model.opt.timestep)
        if steps < 1:
            raise ValueError(
                f"control_frequency_hz {control_frequency_hz} is faster than "
                f"the scene timestep {self._model.opt.timestep}s"
            )
        self._steps_per_control = steps
        self._observation_age_s = (
            self._control_period_s
            if observation_age_s is None
            else float(observation_age_s)
        )

        self._supervision = supervision
        self._held = False
        self._renderer: Optional[object] = None
        self._contact_force = np.zeros(6)
        self._peak_velocity_rps = np.zeros(len(self._dof_index))
        self._peak_force_n = 0.0

        self.reset()

    @property
    def is_real_robot(self) -> bool:
        """False, permanently. Nothing here is evidence about a real G1."""
        return False

    @property
    def joint_names(self) -> tuple[str, ...]:
        return self._joint_names

    @property
    def control_frequency_hz(self) -> float:
        return self._control_frequency_hz

    @property
    def control_period_s(self) -> float:
        return self._control_period_s

    @property
    def held(self) -> bool:
        return self._held

    def describe_configuration(
        self,
        environment_id: str,
        end_effector: str,
        control_authority: str,
        represented_camera_keys: Sequence[str] = (),
    ) -> SimulatedConfiguration:
        """State what this environment is, so a reviewer can find it wrong.

        The facts this object can read off its own compiled model -- whether it
        is hardware, the cadence it steps at, and the joints it commands -- are
        derived here rather than accepted as arguments. A scene that was edited
        or a frequency that was overridden therefore cannot keep a stale
        declaration, which is the entire value of asking the environment
        instead of asking a human.

        The remaining three are claims, and they are arguments because nothing
        in an MJCF file can settle them. ``end_effector`` names the physical
        gripper this geometry stands for, ``control_authority`` names the part
        of the robot the evidence covers, and ``represented_camera_keys`` says
        which of the embodiment's camera keys these rendered views are offered
        as. ``assess_simulation_fidelity`` is what compares them.
        """
        keys = tuple(represented_camera_keys)
        if len(keys) > len(CAMERA_SLOTS):
            raise ValueError(
                f"environment {environment_id!r} claims to represent "
                f"{len(keys)} camera keys, but this simulation renders only "
                f"{len(CAMERA_SLOTS)} slots ({sorted(CAMERA_SLOTS)}); a key "
                "with no view behind it is a claim about nothing"
            )
        return SimulatedConfiguration(
            environment_id=environment_id,
            is_real_robot=self.is_real_robot,
            control_frequency_hz=self._control_frequency_hz,
            controlled_joint_names=self._joint_names,
            end_effector=end_effector,
            control_authority=control_authority,
            represented_camera_keys=keys,
        )

    @property
    def stand_positions_rad(self) -> tuple[float, ...]:
        """The controlled joints' positions in the model's standing keyframe.

        Goal poses are authored against this so a reviewed target is expressed
        as a departure from a known pose rather than as bare numbers.
        """
        return tuple(float(v) for v in self._stand_qpos[self._qpos_index])

    def clock(self) -> float:
        """Simulation time, for a runtime that must not measure wall time.

        A run's elapsed time has to advance with the physics, or a time-limit
        abort would fire based on how busy the host machine was.
        """
        return float(self._data.time)

    def reset(
        self, joint_offsets_rad: Optional[Sequence[float]] = None
    ) -> None:
        """Return to the standing keyframe, optionally displaced, and unlatch.

        ``joint_offsets_rad`` displaces the controlled joints so that repeated
        runs are separate measurements rather than replays of one deterministic
        trajectory. Offsets are clamped to each joint's own model range: a
        perturbation that started the robot outside its mechanical limits would
        make the run a fact about an impossible pose. The commanded target is
        set to the displaced pose too, so the robot holds where it was placed
        instead of springing back to the keyframe before the run begins.
        """
        self._mujoco.mj_resetDataKeyframe(self._model, self._data, 0)
        if joint_offsets_rad is not None:
            self._displace(joint_offsets_rad)
        self._mujoco.mj_forward(self._model, self._data)
        self._held = False
        self._clear_peaks()
        self._accumulate_peaks()

    def _displace(self, joint_offsets_rad: Sequence[float]) -> None:
        """Offset the controlled joints, clamped to their model ranges."""
        if len(joint_offsets_rad) != len(self._qpos_index):
            raise ValueError(
                f"expected {len(self._qpos_index)} joint offsets for "
                f"{self._joint_names}, got {len(joint_offsets_rad)}"
            )
        positions = self._data.qpos[self._qpos_index] + np.asarray(
            joint_offsets_rad, dtype=float
        )
        np.clip(
            positions,
            self._joint_range[:, 0],
            self._joint_range[:, 1],
            out=positions,
        )
        self._data.qpos[self._qpos_index] = positions
        self._data.qvel[:] = 0.0
        self._data.ctrl[self._ctrl_index] = positions

    def declare_supervision(self, supervision: SimulatedSupervision) -> None:
        """Restate the room facts, for instance to simulate a human stop."""
        self._supervision = supervision

    def read_state(self) -> RobotState:
        """Report the state, with velocity and force as within-period peaks.

        Positions and end-effector position are the present. Velocity and force
        are the largest magnitudes seen since the previous read, which is what
        ``RobotState`` requires and what the envelope actually bounds. Reading
        drains the peaks, so each read describes its own interval rather than
        the whole run.
        """
        data = self._data
        peak_velocity, peak_force = self._drain_peaks()
        return RobotState(
            joint_positions_rad=tuple(
                float(v) for v in data.qpos[self._qpos_index]
            ),
            joint_velocity_rps=tuple(float(v) for v in peak_velocity),
            end_effector_force_n=peak_force,
            end_effector_position_m=tuple(
                float(v) for v in data.site_xpos[self._end_effector_site_id]
            ),
            guardian_present=self._supervision.guardian_present,
            estop_engaged=self._supervision.estop_engaged,
            estop_reachable=self._supervision.estop_reachable,
            workspace_clear=self._supervision.workspace_clear,
            age_s=self._observation_age_s,
        )

    def command_joint_positions(self, positions_rad: Sequence[float]) -> None:
        """Apply one waypoint and advance the simulation one control period."""
        self._require_owner_thread("command a simulated robot")
        if self._held:
            raise RuntimeError(
                "this simulated robot was told to hold and will not command "
                "motion again"
            )
        if len(positions_rad) != len(self._ctrl_index):
            raise ValueError(
                f"expected {len(self._ctrl_index)} joint targets for "
                f"{self._joint_names}, got {len(positions_rad)}"
            )
        self._data.ctrl[self._ctrl_index] = np.asarray(
            positions_rad, dtype=float
        )
        for _ in range(self._steps_per_control):
            self._mujoco.mj_step(self._model, self._data)
            self._accumulate_peaks()

    def hold(self) -> None:
        """Latch the current pose as the command target and stop advancing.

        The accumulated peaks survive a hold. They describe motion that really
        happened, and a stop is exactly when a caller most needs to know how
        fast the robot was moving when it was stopped.
        """
        self._data.ctrl[self._ctrl_index] = self._data.qpos[self._qpos_index]
        self._data.qvel[:] = 0.0
        self._mujoco.mj_forward(self._model, self._data)
        self._held = True

    def render(self, slot_id: str) -> np.ndarray:
        """Render one GUI camera slot as a single RGB frame."""
        self._require_owner_thread("render a simulated camera")
        try:
            slot = CAMERA_SLOTS[slot_id]
        except KeyError as error:
            raise KeyError(
                f"unknown camera slot {slot_id!r}; the GUI shows "
                f"{sorted(CAMERA_SLOTS)}"
            ) from error
        renderer = self._ensure_renderer()
        tiles = []
        for source in slot.sources:
            renderer.update_scene(self._data, camera=source)
            tiles.append(renderer.render())
        if len(tiles) == 1:
            return tiles[0]
        return np.hstack(tiles)

    def publish_frames(self, bus: FrameBus) -> None:
        """Render every GUI slot once and hand the frames to the transport."""
        for slot_id in CAMERA_SLOTS:
            bus.publish(slot_id, self.render(slot_id))

    def close(self) -> None:
        renderer = self._renderer
        self._renderer = None
        if renderer is not None:
            renderer.close()

    def _accumulate_peaks(self) -> None:
        """Fold the current instant into the peaks the next read will report."""
        velocity = np.abs(self._data.qvel[self._dof_index])
        np.maximum(self._peak_velocity_rps, velocity, out=self._peak_velocity_rps)
        self._peak_force_n = max(
            self._peak_force_n, self._end_effector_force_n()
        )

    def _drain_peaks(self) -> tuple[np.ndarray, float]:
        """Return the accumulated peaks and start a fresh interval.

        The instant of the read is folded in first, so an interval in which the
        simulation never advanced still reports the present rather than a stale
        zero.
        """
        self._accumulate_peaks()
        velocity = self._peak_velocity_rps.copy()
        force = self._peak_force_n
        self._clear_peaks()
        return velocity, force

    def _clear_peaks(self) -> None:
        self._peak_velocity_rps = np.zeros(len(self._dof_index))
        self._peak_force_n = 0.0

    def _build_model(
        self, end_effector_body: str, offset_m: tuple[float, ...]
    ) -> object:
        mujoco = self._mujoco
        spec = mujoco.MjSpec.from_file(str(self._scene_path))

        keyframe = next(
            (key for key in spec.keys if key.name == _STAND_KEYFRAME), None
        )
        if keyframe is None:
            raise ValueError(
                f"{self._scene_path} has no {_STAND_KEYFRAME!r} keyframe to "
                "start a run from"
            )

        pelvis = spec.find_body("pelvis")
        if pelvis is None:
            raise ValueError(f"{self._scene_path} has no pelvis body to weld")
        free_joints = [
            joint
            for joint in pelvis.joints
            if joint.type == mujoco.mjtJoint.mjJNT_FREE
        ]
        for joint in free_joints:
            keyframe.qpos = np.asarray(keyframe.qpos)[_FREE_BASE_QPOS:]
            keyframe.qvel = np.asarray(keyframe.qvel)[6:]
            joint.delete()
        pelvis.pos = [0.0, 0.0, _PELVIS_STAND_HEIGHT_M]

        self._add_cameras(spec)

        body = spec.find_body(end_effector_body)
        if body is None:
            raise ValueError(
                f"{self._scene_path} has no body {end_effector_body!r} to "
                "attach the end-effector site to"
            )
        site = body.add_site()
        site.name = "end_effector"
        site.pos = list(offset_m)
        site.size = [0.01, 0.0, 0.0]

        model = spec.compile()
        self._stand_qpos = np.array(keyframe.qpos, dtype=float)
        return model

    def _add_cameras(self, spec: object) -> None:
        torso = spec.find_body("torso_link")
        for name, lateral_m in (("head_left", 0.032), ("head_right", -0.032)):
            camera = torso.add_camera()
            camera.name = name
            camera.pos = [0.09, lateral_m, 0.42]
            camera.quat = [0.5, 0.5, -0.5, -0.5]
            camera.fovy = 58.0
        for side in ("left", "right"):
            camera = spec.find_body(f"{side}_wrist_yaw_link").add_camera()
            camera.name = f"{side}_wrist"
            camera.pos = [0.06, 0.0, 0.035]
            camera.quat = [0.5, 0.5, -0.5, -0.5]
            camera.fovy = 70.0

    def _ensure_renderer(self) -> object:
        if self._renderer is None:
            self._renderer = self._mujoco.Renderer(
                self._model, _SOURCE_HEIGHT, _SOURCE_WIDTH
            )
        return self._renderer

    def _resolve_qpos_index(self, names: tuple[str, ...]) -> np.ndarray:
        mujoco = self._mujoco
        indices = []
        for name in names:
            joint = self._require_joint(name)
            if joint.type != mujoco.mjtJoint.mjJNT_HINGE:
                raise ValueError(
                    f"joint {name!r} is not a single-DoF hinge, so it cannot "
                    "be one entry in a joint-position vector"
                )
            indices.append(int(joint.qposadr[0]))
        return np.asarray(indices, dtype=int)

    def _resolve_joint_range(self, names: tuple[str, ...]) -> np.ndarray:
        """Read each controlled joint's own mechanical limits from the model.

        An unlimited joint is reported as an infinite range rather than as its
        stored ``(0, 0)``, which would clamp every perturbation to zero and
        silently turn a varied campaign back into a set of replays.
        """
        ranges = []
        for name in names:
            joint = self._require_joint(name)
            low, high = (float(v) for v in joint.range)
            if not bool(joint.limited) or low >= high:
                low, high = -np.inf, np.inf
            ranges.append((low, high))
        return np.array(ranges, dtype=float)

    def _resolve_dof_index(self, names: tuple[str, ...]) -> np.ndarray:
        return np.asarray(
            [int(self._require_joint(name).dofadr[0]) for name in names],
            dtype=int,
        )

    def _resolve_ctrl_index(self, names: tuple[str, ...]) -> np.ndarray:
        indices = []
        for name in names:
            actuator = self._model.actuator(name)
            if actuator is None:
                raise ValueError(
                    f"joint {name!r} has no position actuator and cannot be "
                    "commanded"
                )
            indices.append(int(actuator.id))
        return np.asarray(indices, dtype=int)

    def _require_joint(self, name: str) -> object:
        try:
            return self._model.joint(name)
        except KeyError as error:
            raise ValueError(
                f"{self._scene_path.name} has no joint named {name!r}"
            ) from error

    def _subtree_geoms(self, body_name: str) -> tuple[int, ...]:
        model = self._model
        root = model.body(body_name).id
        subtree = {root}
        for body_id in range(model.nbody):
            parent = body_id
            while parent != 0:
                if parent in subtree:
                    subtree.add(body_id)
                    break
                parent = int(model.body_parentid[parent])
        return tuple(
            geom_id
            for geom_id in range(model.ngeom)
            if int(model.geom_bodyid[geom_id]) in subtree
        )

    def _end_effector_force_n(self) -> float:
        """Sum contact-force magnitudes on the end-effector subtree.

        This is the quantity the safety envelope bounds, and unlike the
        supervision facts it really is measured: it comes from the contacts the
        solver resolved this step.
        """
        model, data = self._model, self._data
        total = np.zeros(3)
        touched = False
        for contact_id in range(data.ncon):
            contact = data.contact[contact_id]
            if (
                contact.geom1 in self._end_effector_geoms
                or contact.geom2 in self._end_effector_geoms
            ):
                self._mujoco.mj_contactForce(
                    model, data, contact_id, self._contact_force
                )
                total += np.abs(self._contact_force[:3])
                touched = True
        return float(np.linalg.norm(total)) if touched else 0.0

    def _require_owner_thread(self, action: str) -> None:
        if threading.get_ident() != self._owner_thread:
            raise RuntimeError(
                f"cannot {action} from a thread other than the one that "
                "created it; MuJoCo's GL context and data buffer are not "
                "shared, and frames reach other threads through FrameBus"
            )
