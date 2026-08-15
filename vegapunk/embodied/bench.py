"""The assembly: calibration, a goal, a governed loop, and the staged campaigns.

Every module in this package refuses a different way a physical run can be
wrong, and each of them is separately testable because none of them knows how
the others are wired. That independence has a cost, and this module pays it:
until now nothing in the profile assembled the pieces into something a person
could run, so the inner loop existed as a set of parts rather than as a loop.

What it assembles is fixed, and the order is the argument for the module's
existence:

1. ``calibration`` measures how fast this configuration may be commanded, on
   the same displacement the skill will actually fly.
2. that measurement fixes the goal's tolerance floor and the runtime's step
   bound, so the pose being aimed at is one this robot can be observed to reach.
3. ``loop`` runs the skill under the supervisor, against the embodiment the
   evidence will be scoped to.
4. ``campaign`` iterates the simulated stages of the ladder in order, and
   ``admission`` decides what each stage's evidence opened.

Nothing here judges anything. Every verdict in the returned report was produced
by the module that owns it, and the bench's own contribution is to refuse to
proceed when a step's result makes the next step meaningless.

Four refusals:

- It refuses to climb the ladder by seeding it. ``policy_evaluation`` evidence
  is earned by running that stage, not written down so that ``offline_replay``
  becomes reachable. The two stages are distinguished by how far the initial
  condition is perturbed: nominal first, the deployment bound second.
- It refuses to run a VLA skill. There is no policy runtime, and a bench that
  quietly substituted the deterministic one would report evidence about a
  controller under a checkpoint's digest.
- It refuses a calibration that admitted no rate. The alternative is to command
  a rate no probe measured, which is the one piece of arithmetic the
  calibration module exists to prevent.
- It refuses to continue to the next stage when the previous one did not open
  it. Continuing would file evidence for a stage the ladder has already said
  is closed, and the refusal that follows would bury the real reason.

The embodiment is the subtle part. It describes the *simulated* laboratory
configuration, and its facts are read off the compiled model rather than
declared by a human, so nothing about it is unverified in the sense
``unverified_fields`` means. It is not a profile of the physical G1 and cannot
become one: its digest differs, and every record in both ledgers carries that
digest, so no run collected here can ever be read as evidence about the real
robot. Recording the real inventory remains laboratory work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Mapping, Optional, Protocol, Sequence

from vegapunk.embodied.admission import (
    MINIMUM_STAGE_ATTEMPTS,
    STAGE_HARDWARE_SUPERVISED,
    STAGE_OFFLINE_REPLAY,
    STAGE_POLICY_EVALUATION,
    AdmissionDecision,
    AdmissionLedger,
    evaluate_admission,
)
from vegapunk.embodied.calibration import (
    DEFAULT_VELOCITY_MARGIN,
    CalibrationReport,
    CommandRateProbe,
    ProbeMotion,
    calibrate_command_rate,
)
from vegapunk.embodied.campaign import (
    CampaignReport,
    SimulatedCampaignEnvironment,
    SimulationCampaign,
    VariationSchedule,
)
from vegapunk.embodied.embodiment import EmbodimentProfile
from vegapunk.embodied.fidelity import SimulatedConfiguration
from vegapunk.embodied.loop import ExecutionLoop, SkillRuntime
from vegapunk.embodied.runtime import (
    DeterministicJointRuntime,
    JointPoseGoal,
    RobotState,
)
from vegapunk.embodied.safety import SafetyEnvelope, SafetySupervisor
from vegapunk.embodied.skill import (
    SKILL_KIND_DETERMINISTIC,
    PhysicalSkill,
    SkillRegistry,
    SkillSelection,
)
from vegapunk.embodied.trajectory import TrajectoryLedger

BENCH_STAGES = (STAGE_POLICY_EVALUATION, STAGE_OFFLINE_REPLAY)
"""The two stages a simulation may earn, in the order the ladder requires."""

DEFAULT_GOAL_TOLERANCE_RAD = 0.02
"""The goal tolerance used when the measured droop implies a looser one.

A defensible default, not a measured one: it is roughly one degree, which is
the resolution at which a joint-space pose is worth arguing about at all. The
calibration's floor overrides it whenever the servo's droop is larger, so this
constant can only ever make a goal harder to satisfy than the measurement
requires.
"""

DEFAULT_NOMINAL_OFFSET_RAD = 0.01
"""How far ``policy_evaluation`` perturbs the initial condition.

Small enough that a failure is a fact about the controller rather than about
the perturbation. This stage asks whether the thing that authors motion does
what it claims at all.
"""

DEFAULT_DEPLOYMENT_OFFSET_RAD = 0.05
"""How far ``offline_replay`` perturbs the initial condition.

The bound the deployment configuration is expected to absorb. It is wider than
the nominal one on purpose: the two stages would otherwise be the same
measurement reported twice.
"""

DEFAULT_PREVIEW_FPS = 10.0
"""How often a watched run renders, in simulated seconds.

Rendering four camera views costs far more than a control period of physics, so
a run that rendered every step would be a benchmark of the renderer. The cadence
is measured on the simulation clock rather than the wall clock so that watching
a run cannot change the run.
"""

HALTED_NO_ADMITTED_RATE = "no_admitted_command_rate"
HALTED_GOAL_INFEASIBLE = "goal_not_reachable_in_time"
HALTED_STAGE_INCOMPLETE = "stage_incomplete"
HALTED_STAGE_NOT_ADMITTED = "stage_did_not_open_the_next"
HALTED_COMPLETED = "completed"


class SimulatedRobot(Protocol):
    """What the bench needs from an environment, and nothing about MuJoCo.

    Stated as a protocol so this module imports no simulator. The methods split
    cleanly in two: the ones a run uses, which any hardware adapter would also
    provide, and ``reset`` plus ``describe_configuration``, which only a
    simulation can honestly answer.
    """

    @property
    def is_real_robot(self) -> bool:
        """Whether this is hardware. A bench refuses one that says it is."""

    @property
    def joint_names(self) -> tuple[str, ...]:
        """The ordered joints every vector in this bench indexes into."""

    @property
    def control_frequency_hz(self) -> float:
        """The cadence this environment steps at."""

    @property
    def stand_positions_rad(self) -> tuple[float, ...]:
        """The pose goal displacements are expressed as a departure from."""

    def clock(self) -> float:
        """Simulated time, so a run's elapsed time advances with the physics."""

    def reset(
        self, joint_offsets_rad: Optional[Sequence[float]] = None
    ) -> None:
        """Return to the start pose, displaced by the given joint offsets."""

    def read_state(self) -> RobotState:
        """Report the measured state without commanding motion."""

    def command_joint_positions(self, positions_rad: Sequence[float]) -> None:
        """Command one joint-space waypoint."""

    def hold(self) -> None:
        """Stop motion and hold the current pose immediately."""

    def describe_configuration(
        self,
        environment_id: str,
        end_effector: str,
        control_authority: str,
        represented_camera_keys: Sequence[str] = (),
    ) -> SimulatedConfiguration:
        """State what this environment is, so a reviewer can find it wrong."""


class FramePublisher(Protocol):
    """A robot that can render its cameras into a frame bus."""

    def publish_frames(self, bus: object) -> None:
        """Render every camera slot once and hand the frames over."""


@dataclass(frozen=True)
class BenchPlan:
    """One human's declaration of what to iterate, and inside which limits.

    Everything here is a claim a person is accountable for. The facts that can
    be read off the compiled model -- the cadence, the joints, the fact that
    this is not hardware -- are deliberately absent: the bench derives those
    from the environment, so a scene that was edited cannot keep a stale
    declaration.

    ``goal_offsets_rad`` is the reviewed target, expressed as a departure from
    the environment's standing pose rather than as bare joint numbers, so a
    reviewer can see what the motion is. ``satisfies`` names the skill
    postconditions that reaching that pose actually demonstrates; naming one it
    does not is how a controller comes to claim a fact it never measured, which
    the loop's verification step will catch and report as a failure.

    ``envelope`` is not defaulted. The bench assembles measurements; it does not
    invent the limits a supervisor enforces.
    """

    skill: PhysicalSkill
    goal_offsets_rad: tuple[float, ...]
    satisfies: tuple[str, ...]
    envelope: SafetyEnvelope
    candidate_rates_rps: tuple[float, ...]
    environment_id: str
    end_effector: str
    control_authority: str
    camera_map: Mapping[str, str] = field(default_factory=dict)
    attempts_per_stage: int = MINIMUM_STAGE_ATTEMPTS
    velocity_margin: float = DEFAULT_VELOCITY_MARGIN
    nominal_offset_rad: float = DEFAULT_NOMINAL_OFFSET_RAD
    deployment_offset_rad: float = DEFAULT_DEPLOYMENT_OFFSET_RAD

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "goal_offsets_rad",
            tuple(float(value) for value in self.goal_offsets_rad),
        )
        object.__setattr__(self, "satisfies", tuple(self.satisfies))
        object.__setattr__(
            self,
            "candidate_rates_rps",
            tuple(float(value) for value in self.candidate_rates_rps),
        )
        object.__setattr__(self, "camera_map", dict(self.camera_map))

        if self.skill.kind != SKILL_KIND_DETERMINISTIC:
            raise ValueError(
                f"skill {self.skill.version_id!r} is {self.skill.kind!r}; this "
                "bench drives the deterministic joint runtime, and iterating a "
                "policy-authored skill through it would file evidence about "
                "this controller under that checkpoint's digest"
            )
        if self.skill.parameters:
            raise ValueError(
                f"skill {self.skill.version_id!r} declares parameters, but a "
                "bench run drives one reviewed goal pose that is resolved by "
                "skill revision alone; the arguments would be ignored, and an "
                "attempt whose parameters changed nothing is evidence about a "
                "selection nobody made"
            )
        if not any(self.goal_offsets_rad):
            raise ValueError(
                f"the goal for {self.skill.version_id!r} displaces no joint, "
                "so every attempt would begin at its target and measure "
                "nothing"
            )
        if not self.satisfies:
            raise ValueError(
                "a goal pose must name at least one postcondition it "
                "demonstrates, or reaching it proves nothing"
            )
        undeclared = sorted(set(self.satisfies) - set(self.skill.postconditions))
        if undeclared:
            raise ValueError(
                f"the goal claims postcondition(s) {', '.join(undeclared)} "
                f"that skill {self.skill.version_id!r} does not declare"
            )
        if not self.candidate_rates_rps:
            raise ValueError(
                "calibration needs candidate command rates; the bench "
                "proposes none of its own"
            )
        if self.attempts_per_stage < MINIMUM_STAGE_ATTEMPTS:
            raise ValueError(
                f"a stage needs at least {MINIMUM_STAGE_ATTEMPTS} attempts to "
                f"satisfy the admission ladder; {self.attempts_per_stage} "
                "would produce evidence that cannot open anything"
            )
        if not 0 < self.nominal_offset_rad < self.deployment_offset_rad:
            raise ValueError(
                "the deployment stage must perturb the initial condition "
                "further than the nominal one, or the two stages are one "
                "measurement reported twice"
            )

    @property
    def stage_offsets_rad(self) -> Mapping[str, float]:
        """The perturbation bound each simulated stage is measured under."""
        return {
            STAGE_POLICY_EVALUATION: self.nominal_offset_rad,
            STAGE_OFFLINE_REPLAY: self.deployment_offset_rad,
        }


@dataclass(frozen=True)
class BenchReport:
    """What one assembled inner loop measured, and what it opened.

    Every verdict inside was produced by the module that owns it. The bench's
    own contribution is ``halted``: the point at which continuing would have
    filed evidence for a question the previous step had already answered.
    """

    environment_id: str
    skill_version_id: str
    embodiment_digest: str
    calibration: CalibrationReport
    goal: Optional[JointPoseGoal]
    required_duration_s: Optional[float]
    stages: tuple[CampaignReport, ...]
    hardware_decision: Optional[AdmissionDecision]
    halted: str
    halt_detail: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "stages", tuple(self.stages))

    @property
    def completed(self) -> bool:
        """Whether every simulated stage ran and opened the one after it."""
        return self.halted == HALTED_COMPLETED

    @property
    def blocking_hardware(self) -> tuple[str, ...]:
        """What still stands between this configuration and supervised hardware."""
        if self.hardware_decision is None:
            return (self.halt_detail,)
        return self.hardware_decision.blocking_reasons


def embodiment_for(
    robot: SimulatedRobot,
    end_effector: str,
    control_authority: str,
    camera_map: Mapping[str, str],
) -> EmbodimentProfile:
    """Describe the simulated configuration as the profile evidence is scoped to.

    The cadence and the joint count are read from the environment rather than
    declared, which is what makes this profile checkable at all:
    ``assess_simulation_fidelity`` compares the two, and a derived profile
    cannot disagree with the model it was derived from.

    ``unverified_fields`` is empty, and that is a statement about a simulation
    rather than about a robot. Every field here is a fact about a compiled MJCF
    model, which is verified in the only sense that applies to one. The digest
    that results differs from any physical G1's, so nothing collected against
    this profile can be read as evidence about hardware. The real inventory
    remains a laboratory measurement.
    """
    if robot.is_real_robot:
        raise ValueError(
            "refusing to describe a real robot as a simulated configuration; "
            "hardware facts are a laboratory measurement, not a derivation"
        )
    joints = len(robot.joint_names)
    return EmbodimentProfile(
        robot_model="unitree_g1_simulated",
        arm_dof=joints,
        end_effector=end_effector,
        camera_map=dict(camera_map),
        control_frequency_hz=robot.control_frequency_hz,
        control_authority=control_authority,
        state_dim=joints,
        action_dim=joints,
        onboard_image_service=bool(camera_map),
    )


class _WatchedRobot:
    """A robot that renders its cameras as a run advances, on the run's thread.

    Wrapping exists for one reason: MuJoCo renders only on the thread that owns
    its GL context, and that thread is whichever one is stepping the physics.
    Publishing from inside ``command_joint_positions`` is therefore the only
    place a frame can be produced without a second thread touching the
    simulation, and it keeps watching entirely outside the governed loop, which
    must not know whether anyone is looking.

    The cadence is measured on the simulation clock, so a watched run commands
    exactly the same motion as an unwatched one: rendering slows the wall-clock
    pace of the run, never its physics.
    """

    def __init__(
        self,
        robot: SimulatedRobot,
        frames: object,
        fps: float = DEFAULT_PREVIEW_FPS,
    ) -> None:
        if fps <= 0:
            raise ValueError("preview fps must be positive")
        if not callable(getattr(robot, "publish_frames", None)):
            raise TypeError(
                "watching a run needs a robot that can render its cameras; "
                "this environment publishes no frames"
            )
        self._robot = robot
        self._publisher: FramePublisher = robot  # type: ignore[assignment]
        self._frames = frames
        self._interval_s = 1.0 / float(fps)
        self._published_at: Optional[float] = None

    @property
    def is_real_robot(self) -> bool:
        return self._robot.is_real_robot

    @property
    def joint_names(self) -> tuple[str, ...]:
        return self._robot.joint_names

    @property
    def control_frequency_hz(self) -> float:
        return self._robot.control_frequency_hz

    @property
    def stand_positions_rad(self) -> tuple[float, ...]:
        return self._robot.stand_positions_rad

    def clock(self) -> float:
        return self._robot.clock()

    def describe_configuration(
        self,
        environment_id: str,
        end_effector: str,
        control_authority: str,
        represented_camera_keys: Sequence[str] = (),
    ) -> SimulatedConfiguration:
        return self._robot.describe_configuration(
            environment_id=environment_id,
            end_effector=end_effector,
            control_authority=control_authority,
            represented_camera_keys=represented_camera_keys,
        )

    def read_state(self) -> RobotState:
        return self._robot.read_state()

    def reset(
        self, joint_offsets_rad: Optional[Sequence[float]] = None
    ) -> None:
        self._robot.reset(joint_offsets_rad=joint_offsets_rad)
        self._published_at = None
        self._publish()

    def command_joint_positions(self, positions_rad: Sequence[float]) -> None:
        self._robot.command_joint_positions(positions_rad)
        self._publish()

    def hold(self) -> None:
        self._robot.hold()
        self._publish()

    def _publish(self) -> None:
        now = self._robot.clock()
        if (
            self._published_at is not None
            and now - self._published_at < self._interval_s
        ):
            return
        self._published_at = now
        self._publisher.publish_frames(self._frames)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def run_bench(
    robot: SimulatedRobot,
    plan: BenchPlan,
    registry: Optional[SkillRegistry] = None,
    clock: Optional[Callable[[], datetime]] = None,
    frames: Optional[object] = None,
    preview_fps: float = DEFAULT_PREVIEW_FPS,
) -> BenchReport:
    """Measure, then iterate, then report what the ladder opened.

    ``registry`` is accepted rather than always created because the catalog is
    the organisation's, not this run's: a caller with a registry of reviewed
    skills passes it in, and the plan's skill must be a revision that registry
    already holds. Passing none registers the plan's skill in a fresh registry,
    which is the honest reading of a bench operated by one person on one skill.

    ``frames`` turns on the camera preview. It is threaded through to the robot
    rather than to the loop because nothing in the governed path may depend on
    whether a run is being watched.
    """
    at = clock if clock is not None else _utc_now

    embodiment = embodiment_for(
        robot,
        end_effector=plan.end_effector,
        control_authority=plan.control_authority,
        camera_map=plan.camera_map,
    )

    catalog = registry if registry is not None else SkillRegistry()
    if registry is None:
        catalog.register(plan.skill)
    else:
        registered = catalog.get(plan.skill.skill_id, plan.skill.revision)
        if registered.contract_digest() != plan.skill.contract_digest():
            raise ValueError(
                f"the registry holds a different contract for "
                f"{plan.skill.version_id!r} than the plan declares; evidence "
                "would be filed against a revision nobody planned"
            )
    selection = catalog.select(plan.skill.skill_id, {})

    driven: SimulatedRobot = (
        robot
        if frames is None
        else _WatchedRobot(robot, frames, fps=preview_fps)
    )

    # Checked before the offsets are applied, because zip would otherwise
    # truncate silently: a plan carrying one offset too many would produce a
    # correctly shaped target with a joint nobody meant to leave at rest.
    if len(plan.goal_offsets_rad) != len(robot.joint_names):
        raise ValueError(
            f"the plan declares {len(plan.goal_offsets_rad)} joint offsets but "
            f"environment {plan.environment_id!r} commands "
            f"{len(robot.joint_names)} joints "
            f"({', '.join(robot.joint_names)})"
        )
    target = tuple(
        stand + offset
        for stand, offset in zip(
            robot.stand_positions_rad, plan.goal_offsets_rad
        )
    )

    calibration = calibrate_command_rate(
        CommandRateProbe(
            robot=driven,
            motion=ProbeMotion(target_joint_positions_rad=target),
            envelope=plan.envelope,
            control_frequency_hz=robot.control_frequency_hz,
            measured_on=(
                f"{plan.environment_id} at {robot.control_frequency_hz}Hz"
            ),
        ),
        plan.candidate_rates_rps,
        margin=plan.velocity_margin,
    )

    def _report(
        stages: Sequence[CampaignReport],
        halted: str,
        halt_detail: str,
        goal: Optional[JointPoseGoal] = None,
        required_duration_s: Optional[float] = None,
        hardware_decision: Optional[AdmissionDecision] = None,
    ) -> BenchReport:
        return BenchReport(
            environment_id=plan.environment_id,
            skill_version_id=plan.skill.version_id,
            embodiment_digest=embodiment.digest(),
            calibration=calibration,
            goal=goal,
            required_duration_s=required_duration_s,
            stages=tuple(stages),
            hardware_decision=hardware_decision,
            halted=halted,
            halt_detail=halt_detail,
        )

    if calibration.admitted is None:
        return _report(
            (),
            HALTED_NO_ADMITTED_RATE,
            "no candidate rate's measured peak fit the velocity budget "
            f"{calibration.budget_rps:.4f} rad/s, and the bench will not "
            "command a rate no probe measured: "
            + "; ".join(
                f"{item.commanded_rate_rps} rad/s peaked at "
                f"{item.peak_joint_velocity_rps:.4f} rad/s"
                for item in calibration.measurements
            ),
        )

    admitted = calibration.admitted
    goal = JointPoseGoal(
        skill_version_id=plan.skill.version_id,
        target_joint_positions_rad=target,
        satisfies=plan.satisfies,
        tolerance_rad=max(
            DEFAULT_GOAL_TOLERANCE_RAD, admitted.minimum_goal_tolerance_rad
        ),
    )

    def runtime_factory() -> SkillRuntime:
        return DeterministicJointRuntime(
            robot=driven,
            goals=(goal,),
            command_rate=admitted,
            envelope=plan.envelope,
            clock=driven.clock,
        )

    driven.reset()
    required_duration_s = runtime_factory().required_duration_s(selection)
    allowed_duration_s = min(
        plan.envelope.max_duration_s, plan.skill.max_duration_s
    )
    if required_duration_s > allowed_duration_s:
        return _report(
            (),
            HALTED_GOAL_INFEASIBLE,
            f"the goal needs {required_duration_s:.2f}s at "
            f"{admitted.commanded_rate_rps} rad/s, beyond the "
            f"{allowed_duration_s:.2f}s this run is allowed; every attempt "
            "would be aborted partway through its motion and the first one "
            "would quarantine the configuration",
            goal=goal,
            required_duration_s=required_duration_s,
        )

    admission = AdmissionLedger()
    trajectories = TrajectoryLedger()
    loop = ExecutionLoop(
        registry=catalog,
        embodiment=embodiment,
        supervisor=SafetySupervisor(plan.envelope),
        admission=admission,
        trajectories=trajectories,
    )
    configuration = driven.describe_configuration(
        environment_id=plan.environment_id,
        end_effector=plan.end_effector,
        control_authority=plan.control_authority,
        represented_camera_keys=tuple(plan.camera_map),
    )

    stages: list[CampaignReport] = []
    for index, stage in enumerate(BENCH_STAGES):
        campaign = SimulationCampaign(
            loop=loop,
            admission=admission,
            trajectories=trajectories,
            clock=at,
            stage=stage,
        )
        stage_report = campaign.run(
            campaign_id=f"{plan.environment_id}-{stage}",
            selection=selection,
            environment=SimulatedCampaignEnvironment(
                robot=driven,
                runtime_factory=runtime_factory,
                configuration=configuration,
            ),
            schedule=VariationSchedule(
                joint_count=len(robot.joint_names),
                max_offset_rad=plan.stage_offsets_rad[stage],
                seed=index,
            ),
            planned_attempts=plan.attempts_per_stage,
        )
        stages.append(stage_report)

        if not stage_report.completed:
            return _report(
                stages,
                HALTED_STAGE_INCOMPLETE,
                f"stage {stage} stopped after "
                f"{len(stage_report.attempts)} of "
                f"{stage_report.planned_attempts} attempts: "
                f"{stage_report.halt_detail}",
                goal=goal,
                required_duration_s=required_duration_s,
            )
        if not stage_report.next_stage_admitted:
            return _report(
                stages,
                HALTED_STAGE_NOT_ADMITTED,
                f"stage {stage} ran to completion but did not open "
                f"{stage_report.next_stage}: "
                + "; ".join(stage_report.next_stage_blocking_reasons),
                goal=goal,
                required_duration_s=required_duration_s,
            )

    scope = stages[-1].scope
    assert scope is not None
    hardware_decision = evaluate_admission(
        ledger=admission,
        skill_version_id=scope[0],
        embodiment_digest=scope[1],
        policy_digest=scope[2],
        target_stage=STAGE_HARDWARE_SUPERVISED,
        approval=None,
        now=at(),
    )
    return _report(
        stages,
        HALTED_COMPLETED,
        "every simulated stage ran its full plan and opened the next; what "
        "remains before hardware is not simulation work",
        goal=goal,
        required_duration_s=required_duration_s,
        hardware_decision=hardware_decision,
    )
