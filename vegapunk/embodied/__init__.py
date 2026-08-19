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
from vegapunk.embodied.retarget import (
    ACTION_DIM,
    ROTATION_6D_COLUMNS,
    ROTATION_6D_LAYOUTS,
    ROTATION_6D_ROWS,
    TOOL_OFFSET_M,
    ArmRetargeter,
    EndEffectorPose,
    PolicyAction,
    RetargetResult,
    denormalize,
    rotation_from_6d,
    rotation_to_6d,
)
from vegapunk.embodied.runtime import (
    CommandRateCalibration,
    DeterministicJointRuntime,
    JointPoseGoal,
    ResettableRobot,
    RobotInterface,
    RobotState,
)
from vegapunk.embodied.adaptation import (
    DEFAULT_ADAPTATION_SPACE,
    AdaptationCandidate,
    AdaptationSpace,
    AdaptedJointRuntime,
    GoalActionSource,
)
from vegapunk.embodied.harness import (
    DEFAULT_SEARCH_BUDGET,
    SIMULATED_SEARCH_STAGE,
    CampaignEvaluator,
    InvestigationReport,
    investigate,
)
from vegapunk.embodied.hardware import (
    END_EFFECTOR_BRAINCO_REVO2,
    UNOBSERVABLE_OVER_THE_LINK,
    LinkAttestation,
    MotionAuthority,
    PeakAccumulator,
    RealG1,
    observe_link,
)
from vegapunk.embodied.intake import (
    ADAPTATION_PATH_ORDER,
    AUTOMATABLE_PATHS,
    SYMPTOM_ORDER,
    AdaptationBrief,
    PainPoint,
    brief_from_classification,
    triage,
)
from vegapunk.embodied.objective import (
    BucketOutcome,
    CandidateScore,
    RobustnessObjective,
)
from vegapunk.embodied.regime import (
    APPLIED_AXES,
    DEFAULT_CONTACT_REGIME,
    UNAPPLIED_AXES,
    Regime,
    RegimeAxis,
    RegimeSample,
)
from vegapunk.embodied.search import AdaptationSearch, CandidateNode, SearchReport
from vegapunk.embodied.store import DEFAULT_LEDGER_ROOT, LedgerStore
from vegapunk.embodied.trajectory import (
    LabelConfirmation,
    RunClearance,
    TrainingManifest,
    TrajectoryLedger,
    TrajectoryRecord,
)

__all__ = [
    "ACTION_DIM",
    "ADAPTATION_PATH_ORDER",
    "APPLIED_AXES",
    "AUTOMATABLE_PATHS",
    "AdaptationBrief",
    "AdaptationCandidate",
    "AdaptationSearch",
    "AdaptationSpace",
    "AdaptedJointRuntime",
    "ArmRetargeter",
    "AttemptRecord",
    "AttemptVariation",
    "BENCH_STAGES",
    "BenchPlan",
    "BenchReport",
    "BucketOutcome",
    "CalibrationReport",
    "CampaignEnvironment",
    "CampaignEvaluator",
    "CampaignReport",
    "CandidateNode",
    "CandidateScore",
    "CommandRateCalibration",
    "CommandRateProbe",
    "DEFAULT_ADAPTATION_SPACE",
    "DEFAULT_CONTACT_REGIME",
    "DEFAULT_DEPLOYMENT_OFFSET_RAD",
    "DEFAULT_GOAL_TOLERANCE_RAD",
    "DEFAULT_LEDGER_ROOT",
    "DEFAULT_NOMINAL_OFFSET_RAD",
    "DEFAULT_SEARCH_BUDGET",
    "DEFAULT_VELOCITY_MARGIN",
    "DeterministicJointRuntime",
    "END_EFFECTOR_BRAINCO_REVO2",
    "EndEffectorPose",
    "ExecutionLoop",
    "FIDELITY_MISREPRESENTS",
    "FIDELITY_REPRESENTS",
    "FidelityAssessment",
    "GoalActionSource",
    "HALTED_GOAL_INFEASIBLE",
    "HALTED_NO_ADMITTED_RATE",
    "HALTED_STAGE_INCOMPLETE",
    "HALTED_STAGE_NOT_ADMITTED",
    "InvestigationReport",
    "JointPoseGoal",
    "LabelConfirmation",
    "LedgerStore",
    "LinkAttestation",
    "MotionAuthority",
    "PainPoint",
    "PeakAccumulator",
    "PolicyAction",
    "ProbeMotion",
    "ROTATION_6D_COLUMNS",
    "ROTATION_6D_LAYOUTS",
    "ROTATION_6D_ROWS",
    "RealG1",
    "Regime",
    "RegimeAxis",
    "RegimeSample",
    "ResettableRobot",
    "RetargetResult",
    "RobotInterface",
    "RobotState",
    "RobustnessObjective",
    "RunClearance",
    "RunReport",
    "RuntimeStep",
    "SIMULATED_SEARCH_STAGE",
    "SYMPTOM_ORDER",
    "SearchReport",
    "SimulatedCampaignEnvironment",
    "SimulatedConfiguration",
    "SimulatedRobot",
    "SimulationCampaign",
    "SkillRuntime",
    "TOOL_OFFSET_M",
    "TrainingManifest",
    "TrajectoryLedger",
    "TrajectoryRecord",
    "UNAPPLIED_AXES",
    "UNOBSERVABLE_OVER_THE_LINK",
    "UNREPRESENTABLE_IN_SIMULATION",
    "VariationSchedule",
    "assess_simulation_fidelity",
    "brief_from_classification",
    "calibrate_command_rate",
    "denormalize",
    "embodiment_for",
    "investigate",
    "observe_link",
    "rotation_from_6d",
    "rotation_to_6d",
    "run_bench",
    "triage",
]
