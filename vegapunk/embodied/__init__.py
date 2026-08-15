"""Embodied Execution Profile: governed physical execution for a Unitree G1.

Version 1 executes only registered Physical Skills against a verified
embodiment. It does not accept natural language as an execution input and does
not let a language model participate in a motor-control loop.

The profile is seven modules. The first six each refuse a different way a
physical run can be wrong; the last one is the only thing that moves:

``skill``       a reviewed, revision-identified contract with closed parameters
``embodiment``  the checkpoint/robot compatibility facts, verified not assumed
``admission``   the evidence ladder and pinned human approval before hardware
``safety``      deterministic preflight and instantaneous abort authority
``loop``        the single ordered path that applies all of the above
``trajectory``  what a run is allowed to prove afterwards
``runtime``     the deterministic actuation boundary that actually moves joints

Two further modules supply what the ladder needs but cannot invent: an
environment to run in, and a way to iterate in it.

``simulation``   a MuJoCo G1 that can produce ``offline_replay`` runs
``fidelity``     whether that environment is the configuration it claims to be
``calibration``  measures how fast this robot may be told to move
``campaign``     the inner loop that turns varied simulated runs into evidence
``preview``      streams the simulated cameras to the GUI that watches a real G1

One last module composes them. Every other module is independently testable
because none of them knows how the others are wired, and something has to pay
that cost:

``bench``        the assembly: measure, then iterate the ladder's simulated stages
"""

from vegapunk.embodied.bench import (
    BENCH_STAGES,
    DEFAULT_DEPLOYMENT_OFFSET_RAD,
    DEFAULT_GOAL_TOLERANCE_RAD,
    DEFAULT_NOMINAL_OFFSET_RAD,
    HALTED_GOAL_INFEASIBLE,
    HALTED_NO_ADMITTED_RATE,
    HALTED_STAGE_INCOMPLETE,
    HALTED_STAGE_NOT_ADMITTED,
    BenchPlan,
    BenchReport,
    SimulatedRobot,
    embodiment_for,
    run_bench,
)
from vegapunk.embodied.calibration import (
    DEFAULT_VELOCITY_MARGIN,
    CalibrationReport,
    CommandRateProbe,
    ProbeMotion,
    calibrate_command_rate,
)
from vegapunk.embodied.campaign import (
    AttemptRecord,
    AttemptVariation,
    CampaignEnvironment,
    CampaignReport,
    SimulatedCampaignEnvironment,
    SimulationCampaign,
    VariationSchedule,
)
from vegapunk.embodied.fidelity import (
    FIDELITY_MISREPRESENTS,
    FIDELITY_REPRESENTS,
    UNREPRESENTABLE_IN_SIMULATION,
    FidelityAssessment,
    SimulatedConfiguration,
    assess_simulation_fidelity,
)
from vegapunk.embodied.loop import (
    ExecutionLoop,
    RunReport,
    RuntimeStep,
    SkillRuntime,
)
from vegapunk.embodied.runtime import (
    CommandRateCalibration,
    DeterministicJointRuntime,
    JointPoseGoal,
    ResettableRobot,
    RobotInterface,
    RobotState,
)
from vegapunk.embodied.trajectory import (
    LabelConfirmation,
    RunClearance,
    TrainingManifest,
    TrajectoryLedger,
    TrajectoryRecord,
)

__all__ = [
    "AttemptRecord",
    "AttemptVariation",
    "BENCH_STAGES",
    "BenchPlan",
    "BenchReport",
    "CalibrationReport",
    "CampaignEnvironment",
    "CampaignReport",
    "CommandRateCalibration",
    "CommandRateProbe",
    "DEFAULT_DEPLOYMENT_OFFSET_RAD",
    "DEFAULT_GOAL_TOLERANCE_RAD",
    "DEFAULT_NOMINAL_OFFSET_RAD",
    "DEFAULT_VELOCITY_MARGIN",
    "DeterministicJointRuntime",
    "ExecutionLoop",
    "FIDELITY_MISREPRESENTS",
    "FIDELITY_REPRESENTS",
    "FidelityAssessment",
    "HALTED_GOAL_INFEASIBLE",
    "HALTED_NO_ADMITTED_RATE",
    "HALTED_STAGE_INCOMPLETE",
    "HALTED_STAGE_NOT_ADMITTED",
    "JointPoseGoal",
    "LabelConfirmation",
    "ProbeMotion",
    "ResettableRobot",
    "RobotInterface",
    "RobotState",
    "RunClearance",
    "RunReport",
    "RuntimeStep",
    "SimulatedCampaignEnvironment",
    "SimulatedConfiguration",
    "SimulatedRobot",
    "SimulationCampaign",
    "SkillRuntime",
    "TrainingManifest",
    "TrajectoryLedger",
    "TrajectoryRecord",
    "UNREPRESENTABLE_IN_SIMULATION",
    "VariationSchedule",
    "assess_simulation_fidelity",
    "calibrate_command_rate",
    "embodiment_for",
    "run_bench",
]
