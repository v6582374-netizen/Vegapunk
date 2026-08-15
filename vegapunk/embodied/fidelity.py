"""Whether a simulated environment is the configuration it produces evidence for.

The admission ladder rests on one arithmetic fact: evidence is scoped to a
skill revision, an embodiment digest, and a policy digest, so a result obtained
elsewhere can never be read as a result about this robot. ``simulation.py``
supplies the first environment that can produce ``offline_replay`` evidence,
and until now nothing checked that this environment is the configuration the
scope names. A MuJoCo G1 stepping at 200Hz could record evidence against an
embodiment digest declaring 30Hz, and the ladder would count it, because the
digest is a hash of what a human *declared* rather than of what actually ran.

That is the hole this module closes. It compares one environment's declared
facts against one ``EmbodimentProfile`` and reports, per fact, where they
disagree. A disagreement is not a warning: an environment that misrepresents
the configuration cannot produce evidence about it at all, so
``SimulationCampaign`` refuses to iterate in one.

The comparison is deliberately narrow. It checks the facts the evidence rests
on and nothing else:

``is_real_robot``          which stage's evidence this environment may produce
``control_frequency_hz``   the cadence every velocity and duration was measured at
``controlled joints``      the width and identity of every joint vector
``end_effector``           what a contact force is a force on
``control_authority``      which parts of the robot the evidence covers
``camera keys``            the observation stream a learned policy would receive

What it does not check is the far larger set of things a simulation cannot
represent at all. Those are not comparisons that could come out either way, so
they are stated once, unconditionally, in ``UNREPRESENTABLE_IN_SIMULATION`` and
carried in every assessment. A matched fidelity says this is the right
simulator; it never says a simulated run is evidence about physical reality.
That distinction is the ladder's job and stays there: ``offline_replay``
evidence cannot admit hardware execution no matter how faithful the scene.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Optional, Sequence

from vegapunk.embodied.embodiment import EmbodimentProfile

FIDELITY_REPRESENTS = "represents"
FIDELITY_MISREPRESENTS = "misrepresents"

UNREPRESENTABLE_IN_SIMULATION = (
    "room facts: whether a guardian is present, the estop is reachable, and "
    "the workspace is clear are declared by an operator, never measured",
    "contact reality: materials, payload mass, gripper friction and joint "
    "friction are the scene author's approximation, not this laboratory's",
    "perception reality: rendered frames are not photographs of this room, so "
    "a policy's visual robustness is untested here",
    "hardware reality: actuator wear, latency, packet loss and thermal limits "
    "are absent from the model",
)
"""What no simulated run covers, however well the configuration matches.

Stated unconditionally rather than assessed, because none of these could come
out the other way. They are carried in every assessment so a reviewer reading
a campaign's evidence sees what the run did not cover, next to the facts it
did.
"""


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class SimulatedConfiguration:
    """What one simulated environment actually is, as it can be checked.

    Every field is either read from the built model or declared by the person
    who built it, and the split matters. ``control_frequency_hz`` and
    ``controlled_joint_names`` are properties of the loaded scene, so
    ``simulation.describe_configuration`` derives them rather than accepting
    them, and a scene that was edited cannot keep an old declaration.
    ``end_effector``, ``control_authority`` and ``represented_camera_keys`` are
    claims: they say which physical thing the model's geometry stands for, and
    which of the embodiment's camera keys this environment's rendered views are
    offered as. A human makes those claims, and this module's only contribution
    is to make them explicit enough to be wrong.

    ``environment_id`` names the scene build. It travels into the calibration's
    ``measured_on`` and the campaign's evidence notes, so a number can always
    be traced back to the environment that produced it.
    """

    environment_id: str
    is_real_robot: bool
    control_frequency_hz: float
    controlled_joint_names: tuple[str, ...]
    end_effector: str
    control_authority: str
    represented_camera_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "controlled_joint_names", tuple(self.controlled_joint_names)
        )
        object.__setattr__(
            self,
            "represented_camera_keys",
            tuple(self.represented_camera_keys),
        )
        if not self.environment_id:
            raise ValueError(
                "a simulated configuration must name the environment build it "
                "describes; an unnamed environment cannot be traced from the "
                "evidence it produced"
            )
        if self.control_frequency_hz <= 0:
            raise ValueError("control_frequency_hz must be positive")
        if not self.controlled_joint_names:
            raise ValueError(
                f"environment {self.environment_id!r} controls no joints, so "
                "it cannot represent any robot"
            )
        if len(set(self.controlled_joint_names)) != len(
            self.controlled_joint_names
        ):
            raise ValueError(
                f"environment {self.environment_id!r} lists a controlled joint "
                "twice; a joint vector's positions must each mean one joint"
            )
        if not self.end_effector:
            raise ValueError(
                "a simulated configuration must name the end effector its "
                "geometry stands for, or a contact force is a force on nothing"
            )
        if not self.control_authority:
            raise ValueError(
                "a simulated configuration must declare which parts of the "
                "robot it commands, or its evidence covers an unstated scope"
            )

    @property
    def controlled_joint_count(self) -> int:
        return len(self.controlled_joint_names)

    def digest(self) -> str:
        return _digest(
            {
                "environment_id": self.environment_id,
                "is_real_robot": self.is_real_robot,
                "control_frequency_hz": self.control_frequency_hz,
                "controlled_joint_names": list(self.controlled_joint_names),
                "end_effector": self.end_effector,
                "control_authority": self.control_authority,
                "represented_camera_keys": sorted(
                    self.represented_camera_keys
                ),
            }
        )


@dataclass(frozen=True)
class FidelityAssessment:
    """Whether one environment may produce evidence about one embodiment."""

    verdict: str
    environment_id: str
    environment_digest: str
    embodiment_digest: str
    findings: tuple[str, ...] = ()
    unrepresented: tuple[str, ...] = UNREPRESENTABLE_IN_SIMULATION

    def __post_init__(self) -> None:
        object.__setattr__(self, "findings", tuple(self.findings))
        object.__setattr__(self, "unrepresented", tuple(self.unrepresented))

    @property
    def represents(self) -> bool:
        return self.verdict == FIDELITY_REPRESENTS

    def digest(self) -> str:
        return _digest(
            {
                "verdict": self.verdict,
                "environment_digest": self.environment_digest,
                "embodiment_digest": self.embodiment_digest,
                "findings": list(self.findings),
            }
        )


def assess_simulation_fidelity(
    embodiment: EmbodimentProfile,
    environment: SimulatedConfiguration,
    policy_camera_keys: Optional[Sequence[str]] = None,
) -> FidelityAssessment:
    """Compare an environment against the configuration it claims to be.

    ``policy_camera_keys`` is the checkpoint's expected camera keys when a
    learned policy is in scope. It is a separate argument rather than being
    read from the embodiment because the embodiment's ``camera_map`` says which
    cameras the robot *has*, while a policy's contract says which ones its
    observation is built from. A deterministic skill has no such contract and
    passes no keys: an unrendered camera cannot corrupt an observation nothing
    consumes. Omitting the argument therefore checks fewer facts by design, and
    is the honest default rather than a lenient one.
    """
    findings: list[str] = []

    if environment.is_real_robot:
        findings.append(
            f"environment {environment.environment_id!r} reports itself as a "
            "real robot; a fidelity assessment describes a simulation, and a "
            "real run's evidence comes from the ladder's hardware stages "
            "under supervision, not from this comparison"
        )

    if embodiment.unverified_fields:
        findings.append(
            "the embodiment's unverified_fields cannot be represented because "
            "they are not yet facts: "
            + ", ".join(sorted(embodiment.unverified_fields))
        )

    if environment.control_frequency_hz != embodiment.control_frequency_hz:
        findings.append(
            f"environment {environment.environment_id!r} steps at "
            f"{environment.control_frequency_hz}Hz while the embodiment "
            f"declares {embodiment.control_frequency_hz}Hz; every velocity, "
            "duration and command-rate measurement taken here would describe "
            "a different servo cadence than the one the evidence is scoped to"
        )

    if environment.controlled_joint_count < embodiment.arm_dof:
        findings.append(
            f"environment {environment.environment_id!r} commands "
            f"{environment.controlled_joint_count} joints "
            f"({', '.join(environment.controlled_joint_names)}) while the "
            f"embodiment declares {embodiment.arm_dof} arm degrees of "
            "freedom; the joints this environment holds fixed are not "
            "represented, and a skill that needs them was never exercised"
        )

    if environment.end_effector != embodiment.end_effector:
        findings.append(
            f"environment {environment.environment_id!r} models end effector "
            f"{environment.end_effector!r} while the embodiment declares "
            f"{embodiment.end_effector!r}; a contact force measured here is a "
            "force on different geometry"
        )

    if environment.control_authority != embodiment.control_authority:
        findings.append(
            f"environment {environment.environment_id!r} commands "
            f"{environment.control_authority!r} while the embodiment declares "
            f"{embodiment.control_authority!r}; the evidence would cover a "
            "different part of the robot than the scope claims"
        )

    unknown_keys = sorted(
        set(environment.represented_camera_keys) - set(embodiment.camera_map)
    )
    if unknown_keys:
        findings.append(
            f"environment {environment.environment_id!r} offers views for "
            f"camera key(s) {', '.join(repr(key) for key in unknown_keys)} "
            "that the embodiment's camera_map does not contain; a rendered "
            "view standing in for a camera this robot does not have is not a "
            "representation of anything"
        )

    for camera_key in policy_camera_keys or ():
        if camera_key not in environment.represented_camera_keys:
            findings.append(
                f"environment {environment.environment_id!r} renders no view "
                f"for {camera_key!r}, which the policy's observation is built "
                "from; a run here would feed the policy an observation it was "
                "not trained on, so its outcome is not evidence about the "
                "policy"
            )

    verdict = FIDELITY_MISREPRESENTS if findings else FIDELITY_REPRESENTS
    return FidelityAssessment(
        verdict=verdict,
        environment_id=environment.environment_id,
        environment_digest=environment.digest(),
        embodiment_digest=embodiment.digest(),
        findings=tuple(findings),
    )
