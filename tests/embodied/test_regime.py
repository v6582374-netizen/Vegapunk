"""What a regime may claim to have varied, and what it refuses to pretend."""

from __future__ import annotations

import random
import unittest

from vegapunk.embodied.admission import MINIMUM_STAGE_ATTEMPTS
from vegapunk.embodied.regime import (
    APPLIED_AXES,
    AXIS_ACTUATOR_GAIN_SCALE,
    AXIS_COMMAND_LATENCY_STEPS,
    AXIS_DAMPING_SCALE,
    AXIS_FRICTION_SCALE,
    AXIS_JOINT_OFFSET_RAD,
    AXIS_PAYLOAD_KG,
    AXIS_SENSOR_NOISE_RAD,
    DEFAULT_CONTACT_REGIME,
    UNAPPLIED_AXES,
    Regime,
    RegimeAxis,
    RegimeSample,
)


def _axis(name: str = AXIS_FRICTION_SCALE, **overrides: object) -> RegimeAxis:
    fields: dict[str, object] = {
        "name": name,
        "low": 0.8,
        "high": 1.25,
        "unit": "dimensionless",
        "rationale": "a test band, justified only for this test",
    }
    fields.update(overrides)
    return RegimeAxis(**fields)


def _regime(**overrides: object) -> Regime:
    fields: dict[str, object] = {
        "axes": (_axis(),),
        "samples": 4,
        "seed": 3,
    }
    fields.update(overrides)
    return Regime(**fields)


class RegimeAxisTest(unittest.TestCase):
    """One band, and the argument that has to come with it."""

    def test_sample_stays_inside_the_declared_band(self) -> None:
        axis = _axis(low=-0.25, high=0.75)
        generator = random.Random(0)
        for _ in range(200):
            value = axis.sample(generator)
            self.assertGreaterEqual(value, -0.25)
            self.assertLessEqual(value, 0.75)

    def test_the_same_generator_state_draws_the_same_value(self) -> None:
        axis = _axis()
        first = axis.sample(random.Random("seed"))
        second = axis.sample(random.Random("seed"))
        self.assertEqual(first, second)

    def test_a_collapsed_band_is_not_a_distribution(self) -> None:
        with self.assertRaises(ValueError):
            _axis(low=1.0, high=1.0)
        with self.assertRaises(ValueError):
            _axis(low=1.5, high=1.0)

    def test_a_band_without_an_argument_cannot_be_declared(self) -> None:
        with self.assertRaises(ValueError):
            _axis(rationale="")
        with self.assertRaises(ValueError):
            _axis(unit="")
        with self.assertRaises(ValueError):
            _axis(name="")

    def test_digest_tracks_the_band_and_ignores_the_prose(self) -> None:
        """Rewording an argument must not invalidate recorded attempts."""
        baseline = _axis()
        self.assertEqual(
            baseline.digest(),
            _axis(rationale="the same band, argued differently").digest(),
        )
        self.assertNotEqual(baseline.digest(), _axis(high=1.5).digest())
        self.assertNotEqual(baseline.digest(), _axis(unit="rad").digest())


class RegimeSampleTest(unittest.TestCase):
    """One drawn world, and the record an attempt carries."""

    def test_values_cannot_be_edited_after_the_run(self) -> None:
        sample = RegimeSample(index=0, seed=0, values={"friction_scale": 1.0})
        with self.assertRaises(TypeError):
            sample.values["friction_scale"] = 2.0  # type: ignore[index]

    def test_an_absent_axis_reads_as_the_caller_named_default(self) -> None:
        sample = RegimeSample(index=1, seed=1, values={AXIS_PAYLOAD_KG: 0.5})
        self.assertEqual(sample.value(AXIS_PAYLOAD_KG, 0.0), 0.5)
        self.assertEqual(sample.value(AXIS_FRICTION_SCALE, 1.0), 1.0)

    def test_digest_distinguishes_worlds_and_survives_reordering(self) -> None:
        forwards = RegimeSample(
            index=2, seed=5, values={"payload_kg": 0.25, "friction_scale": 1.0}
        )
        backwards = RegimeSample(
            index=2, seed=5, values={"friction_scale": 1.0, "payload_kg": 0.25}
        )
        self.assertEqual(forwards.digest(), backwards.digest())
        moved = RegimeSample(
            index=2, seed=5, values={"payload_kg": 0.26, "friction_scale": 1.0}
        )
        self.assertNotEqual(forwards.digest(), moved.digest())

    def test_a_negative_index_is_not_an_attempt(self) -> None:
        with self.assertRaises(ValueError):
            RegimeSample(index=-1, seed=0, values={})


class RegimeRefusalTest(unittest.TestCase):
    """The four constructions that would report a nominal run as varied."""

    def test_a_regime_that_varies_nothing_is_refused(self) -> None:
        with self.assertRaises(ValueError) as caught:
            _regime(axes=())
        self.assertIn("varies nothing", str(caught.exception))

    def test_a_single_sample_regime_is_refused(self) -> None:
        with self.assertRaises(ValueError) as caught:
            _regime(samples=1)
        self.assertIn("nominal run", str(caught.exception))

    def test_a_duplicated_axis_is_refused(self) -> None:
        with self.assertRaises(ValueError) as caught:
            _regime(axes=(_axis(), _axis(high=1.5)))
        self.assertIn("more than once", str(caught.exception))

    def test_an_unknown_axis_name_is_refused(self) -> None:
        with self.assertRaises(ValueError) as caught:
            _regime(axes=(_axis(name="gravity_scale"),))
        self.assertIn("unknown regime axis", str(caught.exception))

    def test_every_image_space_axis_is_refused_with_its_reason(self) -> None:
        """The refusal has to carry the argument, not just a rejection."""
        for unapplied in UNAPPLIED_AXES:
            with self.subTest(axis=unapplied.name):
                with self.assertRaises(ValueError) as caught:
                    _regime(axes=(_axis(name=unapplied.name),))
                message = str(caught.exception)
                self.assertIn(unapplied.name, message)
                self.assertIn(unapplied.reason, message)

    def test_unapplied_axes_are_disjoint_from_the_applied_registry(
        self,
    ) -> None:
        names = {axis.name for axis in UNAPPLIED_AXES}
        self.assertTrue(names.isdisjoint(APPLIED_AXES))
        for unapplied in UNAPPLIED_AXES:
            self.assertTrue(unapplied.reason)


class RegimeSamplingTest(unittest.TestCase):
    """Reproducibility, independence, and the edge of the declaration."""

    def test_the_same_regime_draws_the_same_worlds(self) -> None:
        first = _regime().sample(2)
        second = _regime().sample(2)
        self.assertEqual(first.digest(), second.digest())
        self.assertEqual(dict(first.values), dict(second.values))

    def test_each_index_is_a_different_world(self) -> None:
        regime = _regime(samples=10)
        digests = {regime.sample(index).digest() for index in range(10)}
        self.assertEqual(len(digests), 10)

    def test_an_index_is_the_same_world_however_many_ran_before_it(
        self,
    ) -> None:
        """A failing attempt must be re-runnable on its own."""
        regime = _regime(samples=8)
        in_sequence = [regime.sample(index) for index in range(8)]
        alone = regime.sample(5)
        self.assertEqual(in_sequence[5].digest(), alone.digest())

    def test_a_different_seed_is_a_different_family(self) -> None:
        self.assertNotEqual(
            _regime(seed=1).sample(0).digest(),
            _regime(seed=2).sample(0).digest(),
        )

    def test_sampling_past_the_declaration_is_refused(self) -> None:
        regime = _regime(samples=4)
        with self.assertRaises(ValueError) as caught:
            regime.sample(4)
        self.assertIn("outside the distribution", str(caught.exception))
        with self.assertRaises(ValueError):
            regime.sample(-1)

    def test_every_declared_axis_appears_in_every_sample(self) -> None:
        regime = Regime(
            axes=(
                _axis(name=AXIS_FRICTION_SCALE),
                _axis(name=AXIS_PAYLOAD_KG, low=0.0, high=1.0, unit="kg"),
            ),
            samples=3,
        )
        self.assertEqual(
            regime.axis_names(), (AXIS_FRICTION_SCALE, AXIS_PAYLOAD_KG)
        )
        for index in range(3):
            self.assertEqual(
                set(regime.sample(index).values), set(regime.axis_names())
            )

    def test_values_stay_inside_their_own_axis_band(self) -> None:
        regime = Regime(
            axes=(
                _axis(name=AXIS_FRICTION_SCALE, low=0.8, high=1.25),
                _axis(name=AXIS_PAYLOAD_KG, low=0.0, high=1.0, unit="kg"),
            ),
            samples=20,
        )
        for index in range(20):
            values = regime.sample(index).values
            self.assertGreaterEqual(values[AXIS_FRICTION_SCALE], 0.8)
            self.assertLessEqual(values[AXIS_FRICTION_SCALE], 1.25)
            self.assertGreaterEqual(values[AXIS_PAYLOAD_KG], 0.0)
            self.assertLessEqual(values[AXIS_PAYLOAD_KG], 1.0)

    def test_digest_pins_the_family_a_report_can_be_compared_against(
        self,
    ) -> None:
        baseline = _regime()
        self.assertEqual(baseline.digest(), _regime().digest())
        self.assertNotEqual(baseline.digest(), _regime(seed=99).digest())
        self.assertNotEqual(baseline.digest(), _regime(samples=5).digest())
        self.assertNotEqual(
            baseline.digest(), _regime(axes=(_axis(high=1.5),)).digest()
        )


class DefaultContactRegimeTest(unittest.TestCase):
    """The starting distribution, and the claims it is allowed to make."""

    def test_it_varies_every_axis_this_profile_applies(self) -> None:
        self.assertEqual(
            set(DEFAULT_CONTACT_REGIME.axis_names()), set(APPLIED_AXES)
        )

    def test_it_draws_one_world_per_required_attempt(self) -> None:
        """Covering the declared distribution exactly once, no world reused."""
        self.assertEqual(DEFAULT_CONTACT_REGIME.samples, MINIMUM_STAGE_ATTEMPTS)

    def test_every_axis_carries_an_argument_and_a_unit(self) -> None:
        for axis in DEFAULT_CONTACT_REGIME.axes:
            with self.subTest(axis=axis.name):
                self.assertTrue(axis.rationale)
                self.assertTrue(axis.unit)
                self.assertLess(axis.low, axis.high)

    def test_the_bands_are_the_ones_that_were_justified(self) -> None:
        """A band that drifts silently makes its rationale a stale claim."""
        bands = {
            axis.name: (axis.low, axis.high)
            for axis in DEFAULT_CONTACT_REGIME.axes
        }
        self.assertEqual(bands[AXIS_JOINT_OFFSET_RAD], (0.0, 0.05))
        self.assertEqual(bands[AXIS_FRICTION_SCALE], (0.8, 1.25))
        self.assertEqual(bands[AXIS_PAYLOAD_KG], (0.0, 1.0))
        self.assertEqual(bands[AXIS_DAMPING_SCALE], (0.5, 2.0))
        self.assertEqual(bands[AXIS_ACTUATOR_GAIN_SCALE], (0.8, 1.25))
        self.assertEqual(bands[AXIS_COMMAND_LATENCY_STEPS], (0.0, 2.0))
        self.assertEqual(bands[AXIS_SENSOR_NOISE_RAD], (0.0, 0.002))

    def test_no_scale_axis_can_draw_a_non_positive_multiplier(self) -> None:
        """A zero friction or gain would fail a run on the perturbation."""
        for name in (
            AXIS_FRICTION_SCALE,
            AXIS_DAMPING_SCALE,
            AXIS_ACTUATOR_GAIN_SCALE,
        ):
            axis = next(
                a for a in DEFAULT_CONTACT_REGIME.axes if a.name == name
            )
            with self.subTest(axis=name):
                self.assertGreater(axis.low, 0.0)

    def test_the_nominal_world_is_inside_the_family(self) -> None:
        """Offsets, payload, latency and noise all reach zero perturbation."""
        for name in (
            AXIS_JOINT_OFFSET_RAD,
            AXIS_PAYLOAD_KG,
            AXIS_COMMAND_LATENCY_STEPS,
            AXIS_SENSOR_NOISE_RAD,
        ):
            axis = next(
                a for a in DEFAULT_CONTACT_REGIME.axes if a.name == name
            )
            with self.subTest(axis=name):
                self.assertEqual(axis.low, 0.0)


if __name__ == "__main__":
    unittest.main()
