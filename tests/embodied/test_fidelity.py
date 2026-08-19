"""Whether an environment may produce evidence about the robot it stands in for."""

from __future__ import annotations

import importlib.util
import unittest

from vegapunk.embodied.embodiment import (
    UNIFOLM_VLA_BASE_G1_EE6D,
    EmbodimentProfile,
)
from vegapunk.embodied.fidelity import (
    FIDELITY_MISREPRESENTS,
    FIDELITY_REPRESENTS,
    UNREPRESENTABLE_IN_SIMULATION,
    SimulatedConfiguration,
    assess_simulation_fidelity,
)

_DEPENDENCIES = ("numpy", "mujoco")
_MISSING = tuple(
    name for name in _DEPENDENCIES if importlib.util.find_spec(name) is None
)

if _MISSING:
    _HAS_SIMULATION = False
    _SKIP_REASON = f"missing simulation dependencies: {', '.join(_MISSING)}"
else:
    from vegapunk.embodied.simulation import DEFAULT_SCENE_PATH

    _HAS_SIMULATION = DEFAULT_SCENE_PATH.exists()
    _SKIP_REASON = f"the G1 MJCF scene is not present at {DEFAULT_SCENE_PATH}"

if _HAS_SIMULATION:
    from vegapunk.embodied.simulation import (
        CAMERA_SLOTS,
        G1_LEFT_ARM_JOINTS,
        SimulatedG1,
        SimulatedSupervision,
    )

_ARM_JOINTS = tuple(f"left_arm_{index}" for index in range(7))


def _embodiment(**overrides: object) -> EmbodimentProfile:
    fields: dict[str, object] = {
        "robot_model": "unitree_g1",
        "arm_dof": 7,
        "end_effector": "dex1_1",
        "camera_map": {"observation.images.top": "head_rgb"},
        "control_frequency_hz": 30.0,
        "control_authority": "arm_and_gripper",
        "state_dim": 16,
        "action_dim": 16,
        "onboard_image_service": True,
    }
    fields.update(overrides)
    return EmbodimentProfile(**fields)


def _environment(**overrides: object) -> SimulatedConfiguration:
    fields: dict[str, object] = {
        "environment_id": "sim-g1-left-arm",
        "is_real_robot": False,
        "control_frequency_hz": 30.0,
        "controlled_joint_names": _ARM_JOINTS,
        "end_effector": "dex1_1",
        "control_authority": "arm_and_gripper",
    }
    fields.update(overrides)
    return SimulatedConfiguration(**fields)


class ConfigurationIsCheckableTests(unittest.TestCase):
    """A description too vague to be wrong is refused at construction."""

    def test_an_unnamed_environment_cannot_be_traced_from_its_evidence(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            _environment(environment_id="")

    def test_an_environment_that_controls_nothing_represents_nothing(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            _environment(controlled_joint_names=())

    def test_a_joint_listed_twice_makes_a_joint_vector_ambiguous(self) -> None:
        with self.assertRaises(ValueError):
            _environment(
                controlled_joint_names=("left_arm_0", "left_arm_0")
            )

    def test_a_force_needs_geometry_it_is_a_force_on(self) -> None:
        with self.assertRaises(ValueError):
            _environment(end_effector="")

    def test_evidence_needs_a_declared_control_authority(self) -> None:
        with self.assertRaises(ValueError):
            _environment(control_authority="")

    def test_a_cadence_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            _environment(control_frequency_hz=0.0)

    def test_the_digest_tracks_every_fact_the_evidence_rests_on(self) -> None:
        baseline = _environment().digest()
        self.assertEqual(baseline, _environment().digest())
        for override in (
            {"control_frequency_hz": 50.0},
            {"controlled_joint_names": _ARM_JOINTS[:5]},
            {"end_effector": "gripper_v2"},
            {"control_authority": "arm_only"},
            {"represented_camera_keys": ("observation.images.top",)},
            {"environment_id": "sim-g1-right-arm"},
        ):
            self.assertNotEqual(
                baseline,
                _environment(**override).digest(),
                f"{override} left the digest unchanged",
            )


class MatchedFidelityTests(unittest.TestCase):
    """What a matched verdict does and does not license."""

    def test_a_matching_environment_may_produce_this_scope_evidence(
        self,
    ) -> None:
        assessment = assess_simulation_fidelity(
            _embodiment(), _environment()
        )
        self.assertEqual(assessment.verdict, FIDELITY_REPRESENTS)
        self.assertTrue(assessment.represents)
        self.assertEqual(assessment.findings, ())

    def test_a_matched_assessment_still_states_what_no_simulation_covers(
        self,
    ) -> None:
        assessment = assess_simulation_fidelity(
            _embodiment(), _environment()
        )
        self.assertEqual(
            assessment.unrepresented, UNREPRESENTABLE_IN_SIMULATION
        )
        self.assertTrue(assessment.unrepresented)

    def test_the_assessment_names_both_configurations_it_compared(
        self,
    ) -> None:
        embodiment = _embodiment()
        environment = _environment()
        assessment = assess_simulation_fidelity(embodiment, environment)
        self.assertEqual(assessment.embodiment_digest, embodiment.digest())
        self.assertEqual(assessment.environment_digest, environment.digest())
        self.assertEqual(assessment.environment_id, environment.environment_id)

    def test_more_joints_than_the_arm_declares_is_not_a_misrepresentation(
        self,
    ) -> None:
        """A scene that also commands the gripper still exercises the arm.

        The check is a floor, not an equality: every joint the embodiment
        declares has to be moveable here. Extra controlled joints mean the
        environment can do more than the arm contract needs, which no run's
        evidence depends on.
        """
        assessment = assess_simulation_fidelity(
            _embodiment(),
            _environment(
                controlled_joint_names=_ARM_JOINTS + ("left_gripper",)
            ),
        )
        self.assertTrue(assessment.represents)


class MisrepresentationTests(unittest.TestCase):
    """Each fact the evidence rests on, disagreed with one at a time."""

    def _findings(self, **overrides: object) -> tuple[str, ...]:
        assessment = assess_simulation_fidelity(
            _embodiment(), _environment(**overrides)
        )
        self.assertEqual(assessment.verdict, FIDELITY_MISREPRESENTS)
        self.assertFalse(assessment.represents)
        return assessment.findings

    def test_a_different_cadence_invalidates_every_measurement_taken_here(
        self,
    ) -> None:
        findings = self._findings(control_frequency_hz=200.0)
        joined = " ".join(findings)
        self.assertIn("200.0", joined)
        self.assertIn("30.0", joined)

    def test_holding_a_declared_arm_joint_fixed_leaves_it_unexercised(
        self,
    ) -> None:
        findings = self._findings(controlled_joint_names=_ARM_JOINTS[:4])
        joined = " ".join(findings)
        self.assertIn("4", joined)
        self.assertIn("7", joined)

    def test_a_force_on_different_geometry_is_a_different_force(self) -> None:
        findings = self._findings(end_effector="parallel_jaw")
        self.assertIn("parallel_jaw", " ".join(findings))

    def test_commanding_a_different_part_of_the_robot_changes_the_scope(
        self,
    ) -> None:
        findings = self._findings(control_authority="whole_body")
        self.assertIn("whole_body", " ".join(findings))

    def test_a_view_for_a_camera_this_robot_lacks_represents_nothing(
        self,
    ) -> None:
        findings = self._findings(
            represented_camera_keys=("observation.images.invented",)
        )
        self.assertIn("observation.images.invented", " ".join(findings))

    def test_every_disagreement_is_reported_not_just_the_first(self) -> None:
        findings = self._findings(
            control_frequency_hz=200.0,
            end_effector="parallel_jaw",
            control_authority="whole_body",
        )
        self.assertEqual(len(findings), 3)

    def test_an_environment_claiming_to_be_hardware_is_not_assessed_here(
        self,
    ) -> None:
        """A fidelity assessment is about a simulation, by construction.

        Passing hardware through this comparison would be a way to obtain a
        matched verdict about a real robot without a supervised run, which is
        the ladder's decision and not this module's.
        """
        findings = self._findings(is_real_robot=True)
        self.assertIn("real robot", " ".join(findings))

    def test_an_unverified_embodiment_fact_cannot_be_represented(self) -> None:
        assessment = assess_simulation_fidelity(
            _embodiment(unverified_fields=("end_effector",)), _environment()
        )
        self.assertFalse(assessment.represents)
        self.assertIn("end_effector", " ".join(assessment.findings))

    def test_the_verdict_and_findings_are_in_the_digest(self) -> None:
        matched = assess_simulation_fidelity(_embodiment(), _environment())
        broken = assess_simulation_fidelity(
            _embodiment(), _environment(control_authority="whole_body")
        )
        self.assertNotEqual(matched.digest(), broken.digest())


class PolicyObservationTests(unittest.TestCase):
    """A learned policy's observation is a stricter contract than the robot's."""

    def _policy_keys(self) -> tuple[str, ...]:
        return UNIFOLM_VLA_BASE_G1_EE6D.expected_camera_keys

    def test_a_policy_camera_the_environment_does_not_render_is_refused(
        self,
    ) -> None:
        assessment = assess_simulation_fidelity(
            _embodiment(),
            _environment(represented_camera_keys=()),
            policy_camera_keys=self._policy_keys(),
        )
        self.assertFalse(assessment.represents)
        self.assertIn("observation.images.top", " ".join(assessment.findings))

    def test_rendering_every_camera_the_policy_consumes_is_enough(
        self,
    ) -> None:
        assessment = assess_simulation_fidelity(
            _embodiment(),
            _environment(represented_camera_keys=self._policy_keys()),
            policy_camera_keys=self._policy_keys(),
        )
        self.assertTrue(assessment.represents)

    def test_a_deterministic_skill_passes_no_camera_contract(self) -> None:
        """Omitting the argument checks fewer facts, which is honest, not lenient.

        A camera nothing consumes cannot corrupt an observation, so an
        unrendered view is not a misrepresentation for a skill that reads no
        images at all.
        """
        assessment = assess_simulation_fidelity(
            _embodiment(), _environment(represented_camera_keys=())
        )
        self.assertTrue(assessment.represents)


@unittest.skipUnless(_HAS_SIMULATION, _SKIP_REASON)
class SimulatedG1DescribesItselfTests(unittest.TestCase):
    """The environment reports the facts it can read off its own model.

    These run against the real MJCF model, because the point of asking the
    environment rather than a human is that an edited scene or an overridden
    frequency cannot keep a stale declaration.
    """

    def _robot(self, **overrides: object) -> "SimulatedG1":
        robot = SimulatedG1(
            supervision=SimulatedSupervision(
                guardian_present=True,
                estop_engaged=False,
                estop_reachable=True,
                workspace_clear=True,
            ),
            **overrides,
        )
        self.addCleanup(robot.close)
        return robot

    def _describe(self, robot: "SimulatedG1") -> SimulatedConfiguration:
        return robot.describe_configuration(
            environment_id="menagerie-g1-left-arm",
            end_effector="dex1_1",
            control_authority="arm_and_gripper",
        )

    def test_the_derived_facts_come_from_the_built_model(self) -> None:
        robot = self._robot(control_frequency_hz=30.0)
        configuration = self._describe(robot)
        self.assertFalse(configuration.is_real_robot)
        self.assertEqual(configuration.control_frequency_hz, 30.0)
        self.assertEqual(
            configuration.controlled_joint_names, G1_LEFT_ARM_JOINTS
        )

    def test_an_overridden_cadence_cannot_be_described_as_the_old_one(
        self,
    ) -> None:
        slow = self._describe(self._robot(control_frequency_hz=30.0))
        fast = self._describe(self._robot(control_frequency_hz=50.0))
        self.assertEqual(fast.control_frequency_hz, 50.0)
        self.assertNotEqual(slow.digest(), fast.digest())

    def test_a_narrower_scene_reports_the_joints_it_actually_commands(
        self,
    ) -> None:
        robot = self._robot(controlled_joints=G1_LEFT_ARM_JOINTS[:4])
        configuration = self._describe(robot)
        self.assertEqual(configuration.controlled_joint_count, 4)

    def test_more_camera_claims_than_rendered_slots_is_refused(self) -> None:
        robot = self._robot()
        with self.assertRaises(ValueError):
            robot.describe_configuration(
                environment_id="menagerie-g1-left-arm",
                end_effector="dex1_1",
                control_authority="arm_and_gripper",
                represented_camera_keys=tuple(
                    f"observation.images.{index}"
                    for index in range(len(CAMERA_SLOTS) + 1)
                ),
            )

    def test_the_described_environment_matches_a_matching_embodiment(
        self,
    ) -> None:
        robot = self._robot(control_frequency_hz=30.0)
        assessment = assess_simulation_fidelity(
            _embodiment(arm_dof=len(G1_LEFT_ARM_JOINTS)),
            self._describe(robot),
        )
        self.assertTrue(assessment.represents, assessment.findings)


if __name__ == "__main__":
    unittest.main()
