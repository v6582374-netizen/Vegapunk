"""The distribution one attempt is drawn from, and the axes it refuses to fake.

``fidelity.py`` states what no simulated run covers, and two of its entries are
listed as permanent facts about simulation when they are really facts about a
*scene*. Contact reality -- friction, payload mass, joint dissipation -- and
part of hardware reality -- servo gain spread and command latency -- are things
this physics engine can express and simply was not asked to vary. Left as
disclaimers they license the quietest overfit available to a search: succeed in
one nominal world, ten times, and report ten independent successes. This module
converts each of those disclaimers into a sampled range, so that a campaign's
success rate is a statement about a band of worlds rather than about the one
the scene author happened to author.

The conversion is deliberately partial, and the boundary is the point. An axis
belongs here only if the simulator genuinely applies it and something in the
run genuinely reads it. Lighting, texture, camera extrinsics and image noise
all fail that test today, because nothing in Version 1 consumes an image in a
control loop, and they are therefore named in ``UNAPPLIED_AXES`` and rejected
by name. A randomization axis that is sampled, digested, and reported but never
reaches the physics is worse than an absent one: it manufactures the appearance
of robustness evidence, and it does so in the artefact a reviewer trusts most.

Four refusals:

- It refuses a regime of one sample. A distribution evaluated at a single point
  is a nominal run wearing a distribution's name, and it would make the
  per-attempt digest look varied while every attempt shared a world.
- It refuses a degenerate axis. ``low >= high`` collapses the axis to a
  constant, which is the same lie one layer down.
- It refuses duplicate and unknown axis names. A sample is matched to the
  simulator's applier by name, so a misspelling would otherwise be silently
  dropped and the attempt would run nominal while claiming otherwise.
- It refuses the image-space axes explicitly rather than by omission, with the
  reason attached, so that adding a policy that reads frames is a decision
  someone makes against a stated argument instead of a gap they never saw.

A regime is a per-attempt fact and never a configuration fact. The
configuration digest is the anchor every piece of evidence is scoped to, so a
regime that entered it would make each attempt a different configuration and
dissolve the evidence set the ladder counts.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

AXIS_JOINT_OFFSET_RAD = "joint_offset_rad"
AXIS_FRICTION_SCALE = "friction_scale"
AXIS_PAYLOAD_KG = "payload_kg"
AXIS_DAMPING_SCALE = "damping_scale"
AXIS_ACTUATOR_GAIN_SCALE = "actuator_gain_scale"
AXIS_COMMAND_LATENCY_STEPS = "command_latency_steps"
AXIS_SENSOR_NOISE_RAD = "sensor_noise_rad"

APPLIED_AXES = (
    AXIS_JOINT_OFFSET_RAD,
    AXIS_FRICTION_SCALE,
    AXIS_PAYLOAD_KG,
    AXIS_DAMPING_SCALE,
    AXIS_ACTUATOR_GAIN_SCALE,
    AXIS_COMMAND_LATENCY_STEPS,
    AXIS_SENSOR_NOISE_RAD,
)
"""The registry: every axis some simulator in this profile actually applies.

This is the authority a ``Regime`` validates against, and
``simulation.SUPPORTED_PERTURBATION_AXES`` is derived from it rather than
restated, so the list of axes that may be sampled cannot drift away from the
list of axes that are honoured.
"""


@dataclass(frozen=True)
class UnappliedAxis:
    """An axis this profile can name but refuses to sample, and why not.

    Kept as data rather than as a comment because the refusal has to reach the
    person who tries to use the axis. ``Regime`` quotes ``reason`` back at them
    at construction, which is the only moment the argument is worth anything.
    """

    name: str
    reason: str


UNAPPLIED_AXES = (
    UnappliedAxis(
        name="lighting",
        reason=(
            "light position, colour and intensity change only rendered "
            "pixels, and no Version 1 control loop reads a pixel"
        ),
    ),
    UnappliedAxis(
        name="texture",
        reason=(
            "surface appearance is decoupled from contact dynamics in MuJoCo, "
            "so varying it moves an image and nothing a run measures"
        ),
    ),
    UnappliedAxis(
        name="camera_extrinsics",
        reason=(
            "the cameras feed the preview transport a human watches, not the "
            "controller, so shifting them varies the view and not the run"
        ),
    ),
    UnappliedAxis(
        name="image_noise",
        reason=(
            "sensor noise on a frame is only a perturbation once a policy "
            "consumes frames; today it would perturb a picture of the run"
        ),
    ),
)
"""The image-space axes, refused by name until something reads an image.

Every entry would be trivial to sample and would show up in an attempt digest
looking like robustness evidence. None of them reaches the physics or the
controller, so each one would be a claim about coverage the run does not have.
They are listed rather than omitted so that admitting a frame-consuming policy
forces someone to argue with this text.
"""

_UNAPPLIED_BY_NAME: Mapping[str, str] = MappingProxyType(
    {axis.name: axis.reason for axis in UNAPPLIED_AXES}
)

_MINIMUM_SAMPLES = 2
"""Below this a regime is a nominal run with extra ceremony.

Two is the smallest number that can disagree with itself. It is a floor, not a
recommendation: ``DEFAULT_CONTACT_REGIME`` draws far more.
"""

_DIGEST_LENGTH = 16
"""Digest width, matched to the rest of the profile so anchors look alike."""

_DEFAULT_REGIME_SAMPLES = 10
"""Worlds in ``DEFAULT_CONTACT_REGIME``, matched to the ladder's attempt floor.

``admission.MINIMUM_STAGE_ATTEMPTS`` is ten, so ten samples means one world per
attempt: the evidence set covers the distribution once, with no world counted
twice and none of the declared band left undrawn.
"""

_VALUE_PRECISION = 9
"""Rounding applied before digesting, so a digest survives float printing.

Nine decimal places is far finer than any quantity here is known to, and far
coarser than the last bits of a double, which is exactly the property a stable
identifier needs.
"""


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:_DIGEST_LENGTH]


@dataclass(frozen=True)
class RegimeAxis:
    """One physical quantity, the band it varies over, and the case for it.

    ``rationale`` is a required field rather than documentation because the
    width of the band is the whole claim. A range chosen wide enough to fail
    the skill says nothing about the skill, and a range chosen narrow enough to
    guarantee success says nothing at all; the only defence against either is a
    stated argument a reviewer can reject.
    """

    name: str
    low: float
    high: float
    unit: str
    rationale: str

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("a regime axis requires a name")
        if not self.unit:
            raise ValueError(
                f"axis {self.name!r} declares no unit; a bare number cannot "
                "be checked against a physical claim"
            )
        if not self.rationale:
            raise ValueError(
                f"axis {self.name!r} declares no rationale, so nothing states "
                "why this band and not a wider one"
            )
        if self.low >= self.high:
            raise ValueError(
                f"axis {self.name!r} spans [{self.low}, {self.high}], which "
                "is a constant rather than a distribution; a regime built "
                "from it would report varied attempts that shared one world"
            )

    def sample(self, generator: random.Random) -> float:
        """Draw one value, uniformly.

        Uniform rather than normal because these bands are statements about
        plausible extremes, not about a measured central tendency. Nothing here
        was measured on this laboratory's robot, so a distribution with tails
        would be inventing a confidence nobody established.
        """
        return generator.uniform(self.low, self.high)

    def digest(self) -> str:
        """Identify the band, not the prose that justifies it.

        ``rationale`` is excluded on purpose: rewording an argument does not
        change which worlds get drawn, and a digest that moved when the prose
        moved would make every stored attempt look stale after a typo fix.
        """
        return _digest(
            {
                "name": self.name,
                "low": round(self.low, _VALUE_PRECISION),
                "high": round(self.high, _VALUE_PRECISION),
                "unit": self.unit,
            }
        )


@dataclass(frozen=True)
class RegimeSample:
    """One world, drawn once, reproducible from its seed.

    This is what an attempt actually ran in, and it travels with the attempt so
    that a campaign which found a failure can be re-run in the world that
    produced it. ``values`` is a read-only mapping because a sample that could
    be edited after the run would let the record disagree with the physics.
    """

    index: int
    seed: int
    values: Mapping[str, float]

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("a sample index cannot be negative")
        object.__setattr__(
            self,
            "values",
            MappingProxyType(
                {
                    str(name): float(value)
                    for name, value in sorted(self.values.items())
                }
            ),
        )

    def value(self, name: str, default: float) -> float:
        """Read one axis, falling back to the unperturbed value.

        The default is required rather than optional so that every caller has
        to name the value that means "this axis was not varied". An implicit
        zero would silently zero a scale factor and stall the robot.
        """
        return float(self.values.get(name, default))

    def digest(self) -> str:
        return _digest(
            {
                "index": self.index,
                "seed": self.seed,
                "values": {
                    name: round(value, _VALUE_PRECISION)
                    for name, value in self.values.items()
                },
            }
        )


@dataclass(frozen=True)
class Regime:
    """A bounded family of worlds, and the count of them a campaign will see.

    ``seed`` makes the family reproducible and ``samples`` fixes its size, both
    of which are recorded in ``digest``. Two campaigns whose reports carry the
    same regime digest drew the same worlds in the same order, which is what
    makes their success rates comparable at all.
    """

    axes: tuple[RegimeAxis, ...]
    samples: int
    seed: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "axes", tuple(self.axes))
        if not self.axes:
            raise ValueError(
                "a regime with no axes varies nothing, so every attempt drawn "
                "from it would replay one world while reporting a "
                "distribution"
            )
        names = [axis.name for axis in self.axes]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise ValueError(
                f"regime declares axis names more than once: {duplicates}; "
                "the later definition would silently win and the earlier "
                "band would be reported but never drawn"
            )
        for name in names:
            self._require_supported(name)
        if self.samples < _MINIMUM_SAMPLES:
            raise ValueError(
                f"a regime needs at least {_MINIMUM_SAMPLES} samples, got "
                f"{self.samples}; one sample is a nominal run wearing a "
                "distribution's name"
            )

    @staticmethod
    def _require_supported(name: str) -> None:
        reason = _UNAPPLIED_BY_NAME.get(name)
        if reason is not None:
            raise ValueError(
                f"axis {name!r} is deliberately not applied by this profile: "
                f"{reason}. Sampling it would put a robustness claim in the "
                "attempt record that no part of the run can honour"
            )
        if name not in APPLIED_AXES:
            raise ValueError(
                f"unknown regime axis {name!r}; this profile applies "
                f"{sorted(APPLIED_AXES)}. An axis no simulator reads would be "
                "sampled, digested and then dropped"
            )

    def axis_names(self) -> tuple[str, ...]:
        return tuple(axis.name for axis in self.axes)

    def sample(self, index: int) -> RegimeSample:
        """Draw world ``index``, independently of every other index.

        Each index gets its own generator, keyed by the regime seed and the
        index, so that attempt seven is the same world whether or not attempts
        one to six were run. A single stream shared across indices would make
        a re-run of one failing attempt a different world.
        """
        if index < 0:
            raise ValueError("a sample index cannot be negative")
        if index >= self.samples:
            raise ValueError(
                f"regime declares {self.samples} samples, so index {index} "
                "is outside the distribution a reviewer was shown"
            )
        generator = random.Random(f"{self.seed}:{index}")
        return RegimeSample(
            index=index,
            seed=self.seed + index,
            values={
                axis.name: axis.sample(generator) for axis in self.axes
            },
        )

    def digest(self) -> str:
        return _digest(
            {
                "axes": [axis.digest() for axis in self.axes],
                "samples": self.samples,
                "seed": self.seed,
            }
        )


DEFAULT_CONTACT_REGIME = Regime(
    axes=(
        RegimeAxis(
            name=AXIS_JOINT_OFFSET_RAD,
            low=0.0,
            high=0.05,
            unit="rad",
            rationale=(
                "the magnitude bound on the initial joint displacement, "
                "matched to the deployment offset the profile already uses "
                "(about three degrees). Starting from zero keeps the nominal "
                "pose inside the family rather than excluding it, and the "
                "upper bound stays inside every controlled joint's reviewed "
                "operating region so a failure is a fact about the skill and "
                "not about an impossible start pose"
            ),
        ),
        RegimeAxis(
            name=AXIS_FRICTION_SCALE,
            low=0.8,
            high=1.25,
            unit="dimensionless",
            rationale=(
                "plus or minus a quarter on the scene author's guessed "
                "contact "
                "coefficients, which is the honest width for a number nobody "
                "measured on this laboratory's gripper or table. Measured on "
                "this scene, a press that peaks near 3.9N nominal reaches "
                "about 7.3N at 0.8 and about 15N at 0.6, so a wider band "
                "would "
                "abort runs against the 20N envelope on the perturbation "
                "rather than on the skill"
            ),
        ),
        RegimeAxis(
            name=AXIS_PAYLOAD_KG,
            low=0.0,
            high=1.0,
            unit="kg",
            rationale=(
                "an empty gripper through a modest handheld object, against a "
                "0.46kg nominal end-effector link and a 25Nm elbow actuator "
                "limit. Measured on this scene, 1kg raises resting droop from "
                "0.0038 to 0.0056 rad, still comfortably inside the 0.02 rad "
                "goal tolerance, so the payload does not by itself fail a "
                "pose the servo actually reached"
            ),
        ),
        RegimeAxis(
            name=AXIS_DAMPING_SCALE,
            low=0.5,
            high=2.0,
            unit="dimensionless",
            rationale=(
                "a factor of two either way on joint dissipation, which is a "
                "lubrication-and-wear quantity that varies by roughly that "
                "much over a real joint's life and is pure guesswork in an "
                "MJCF file. The band is deliberately wider than the contact "
                "one because its measured effect on this scene is small: it "
                "moves tracking error by well under a milliradian"
            ),
        ),
        RegimeAxis(
            name=AXIS_ACTUATOR_GAIN_SCALE,
            low=0.8,
            high=1.25,
            unit="dimensionless",
            rationale=(
                "plus or minus a quarter on the position servo's stiffness, "
                "covering unit-to-unit spread and warm-versus-cold gain drift "
                "on a real drive. Measured on this scene the band spans "
                "0.0047 to 0.0030 rad of resting droop and 0.86 to 0.89 rad/s "
                "of peak velocity, so it stays inside both the 0.02 rad goal "
                "tolerance and the 1.5 rad/s envelope: the axis stresses the "
                "controller without deciding the run's outcome by itself"
            ),
        ),
        RegimeAxis(
            name=AXIS_COMMAND_LATENCY_STEPS,
            low=0.0,
            high=2.0,
            unit="control steps",
            rationale=(
                "nought to two control periods, which at the profile's 50Hz "
                "cadence is nought to 40ms: the range a command actually "
                "spends crossing a real G1's transport before the servo sees "
                "it. Two is the upper bound because a lag longer than the "
                "period it was planned against stops being a plant property "
                "and becomes a broken link, which belongs in an abort test "
                "and not in a robustness distribution"
            ),
        ),
        RegimeAxis(
            name=AXIS_SENSOR_NOISE_RAD,
            low=0.0,
            high=0.002,
            unit="rad",
            rationale=(
                "up to about 0.11 degrees of standard deviation on reported "
                "joint angle, the order of a production joint encoder's "
                "quantisation and electrical noise. Three sigma at the top of "
                "the band is 0.006 rad, which added to the worst measured "
                "droop in this regime stays under the 0.02 rad goal "
                "tolerance, so noise degrades the measurement without turning "
                "a reached pose into a reported failure"
            ),
        ),
    ),
    samples=_DEFAULT_REGIME_SAMPLES,
)
"""A defensible starting distribution over everything this profile applies.

Ten samples because the ladder already requires ten attempts per stage, so a
campaign that draws one world per attempt covers the regime exactly once. Every
band is justified on its own axis; together they are deliberately survivable.
The point of a first regime is to find out whether a skill that works nominally
works at all off-nominal, and a family tuned to break it would answer a
question nobody asked.
"""
