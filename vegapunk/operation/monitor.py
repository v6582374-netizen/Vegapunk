"""The Instrument Monitor: a veto in the actuation path, not a sequencer.

The named states of this loop -- lid open, cup held, transfer complete, cup
released, lid closed -- describe the task, so the reflex is to make them the
sequence the run executes: reach state, verify, authorise the next. That reflex
rebuilds the scripted point-to-point behaviour that already works today, wraps a
learned policy around it, and gains nothing. If a supervisor authorises each
step, the policy is a gesture library with extra latency, and the continuous
walk-and-operate behaviour this whole effort exists to teach can never appear.

So this monitor observes; it does not advance. Its only authority is **hold**.

Gating is negative, because only one act is irreversible
--------------------------------------------------------
Almost every transition in this loop is recoverable: a wrongly-opened lid closes
again, a badly-grasped cup goes back down, a mistimed button press is pressed
again. Recoverable transitions do not need permission -- they need to be
recorded and to be interruptible. Spending a weak perceptual budget proving six
facts buys nothing.

Exactly one act cannot be undone: the pour. Liquid leaves the cup once, and
pouring onto a closed lid is the failure that matters. That collapses
verification to a single question -- is the lid open -- which is also the most
observable fact in the scene: binary, static, large, and changed only by a
deliberate button press.

How the gate is enforced without segmenting the run
---------------------------------------------------
The monitor sits in the actuation path and inspects the frame *about to be
published*. A pour is not an abstract phase, it is a physical posture: the hand
closed around the cup and the wrist rolled past the angle at which liquid
leaves it. The monitor recognises that posture in the commanded target and vetoes
the frame unless the witness says the lid is open.

That is a veto on one class of frames, not a state machine driving the robot. The
policy stays continuous and unsegmented; it simply cannot execute the one
irreversible act into an unverified world. Every other frame passes untouched.

``PourPosture``      what "about to pour" means, in target values
``InstrumentMonitor``  the veto, and the hold it produces
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from vegapunk.operation.target import (
    G1_JOINT_NAMES,
    HAND_JOINT_NAMES,
    WholeBodyTarget,
)
from vegapunk.operation.witness import IndependentWitness, WitnessVerdict

_JOINT_BASE = 6

LEFT_WRIST_ROLL = _JOINT_BASE + G1_JOINT_NAMES.index("left_wrist_roll_joint")
RIGHT_WRIST_ROLL = _JOINT_BASE + G1_JOINT_NAMES.index("right_wrist_roll_joint")

_GRASP_FINGERS = tuple(
    HAND_JOINT_NAMES.index(name) for name in ("index", "middle", "ring", "pinky")
)

PASS = "pass"
HOLD_LID_NOT_OPEN = "hold_lid_not_open"

DEFAULT_GRASP_CLOSURE_RAD = 0.6
"""How closed the fingers must be to count as holding the cup.

The Revo2 fingers run 0 to about 1.47 rad, so this is a firm grasp rather than a
hand merely on its way somewhere. Set below a full close because a hand holding a
rigid cup does not reach its unloaded limit.
"""

DEFAULT_POUR_TILT_RAD = 0.7
"""How far the wrist must be rolled to count as pouring.

Roughly 40 degrees: past the angle at which an open vessel spills and well short
of the joint's 1.97 rad limit, so a hand carrying a cup level does not trip it.
"""


@dataclass(frozen=True)
class PourPosture:
    """The physical definition of the loop's one irreversible act.

    It is expressed in commanded target values rather than as a task phase,
    because the monitor must recognise the act from the frame in front of it
    without being told what the policy thinks it is doing. A policy that
    mislabels its own phase is exactly the case a gate has to survive.
    """

    grasp_closure_rad: float = DEFAULT_GRASP_CLOSURE_RAD
    pour_tilt_rad: float = DEFAULT_POUR_TILT_RAD

    def __post_init__(self) -> None:
        if self.grasp_closure_rad <= 0:
            raise ValueError("grasp_closure_rad must be positive")
        if self.pour_tilt_rad <= 0:
            raise ValueError("pour_tilt_rad must be positive")

    def _grasping(self, hand: tuple[float, ...]) -> bool:
        return all(hand[index] >= self.grasp_closure_rad for index in _GRASP_FINGERS)

    def detect(self, target: WholeBodyTarget) -> Optional[str]:
        """Name the hand about to pour, or ``None`` if no hand is.

        Either hand can hold the cup. Nothing in this loop privileges one, and a
        gate that only watched the expected hand would be defeated by a policy
        that learned the other.
        """
        for label, hand, roll_index in (
            ("left", target.left_hand, LEFT_WRIST_ROLL),
            ("right", target.right_hand, RIGHT_WRIST_ROLL),
        ):
            if not self._grasping(hand):
                continue
            if abs(target.body[roll_index]) >= self.pour_tilt_rad:
                return label
        return None


@dataclass(frozen=True)
class MonitorVerdict:
    """What the monitor decided about one frame."""

    decision: str
    detail: str = ""
    lid: str = ""
    pouring_hand: Optional[str] = None

    @property
    def holds(self) -> bool:
        return self.decision != PASS


class InstrumentMonitor:
    """Deterministic. No learned component, and no language model in this path.

    Given one frame and the witness, it returns either ``PASS`` or a hold. It
    holds no task state, counts no steps, and cannot advance anything -- so it
    structurally cannot become the sequencer this design rejects.
    """

    def __init__(
        self,
        witness: IndependentWitness,
        *,
        posture: Optional[PourPosture] = None,
    ) -> None:
        self._witness = witness
        self._posture = posture or PourPosture()
        self._last: Optional[WitnessVerdict] = None

    @property
    def witness_identity(self) -> str:
        return self._witness.identity

    @property
    def last_lid(self) -> str:
        return "" if self._last is None else self._last.value

    def preflight_witness(self) -> WitnessVerdict:
        """Read the same Independent Witness before a supervised episode."""
        verdict = self._witness.observe()
        self._last = verdict
        return verdict

    def evaluate(self, target: WholeBodyTarget) -> MonitorVerdict:
        """Judge one frame on its way to the bridge.

        The witness is only consulted when the gate is actually in play. A run
        that never reaches a pour posture never depends on the lid bit, so a
        witness outage during the approach is not a reason to stop the robot.
        """
        hand = self._posture.detect(target)
        if hand is None:
            return MonitorVerdict(PASS)

        verdict = self._witness.observe()
        self._last = verdict
        if verdict.open:
            return MonitorVerdict(
                PASS, verdict.detail, lid=verdict.value, pouring_hand=hand
            )
        return MonitorVerdict(
            HOLD_LID_NOT_OPEN,
            f"the {hand} hand is in a pour posture but the lid is "
            f"{verdict.value}: {verdict.detail}",
            lid=verdict.value,
            pouring_hand=hand,
        )
