"""Embodied Execution Profile: governed physical execution for a Unitree G1.

Version 1 executes only registered Physical Skills against a verified
embodiment. It does not accept natural language as an execution input and does
not let a language model participate in a motor-control loop.

The profile is five layers, each refusing a different way a physical run can be
wrong:

``skill``       a reviewed, revision-identified contract with closed parameters
``embodiment``  the checkpoint/robot compatibility facts, verified not assumed
``admission``   the evidence ladder and pinned human approval before hardware
``safety``      deterministic preflight and instantaneous abort authority
``loop``        the single ordered path that applies all of the above
``trajectory``  what a run is allowed to prove afterwards
"""

from vegapunk.embodied.loop import (
    ExecutionLoop,
    RunReport,
    RuntimeStep,
    SkillRuntime,
)
from vegapunk.embodied.trajectory import (
    LabelConfirmation,
    RunClearance,
    TrainingManifest,
    TrajectoryLedger,
    TrajectoryRecord,
)

__all__ = [
    "ExecutionLoop",
    "LabelConfirmation",
    "RunClearance",
    "RunReport",
    "RuntimeStep",
    "SkillRuntime",
    "TrainingManifest",
    "TrajectoryLedger",
    "TrajectoryRecord",
]
