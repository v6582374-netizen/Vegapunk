from __future__ import annotations

import unittest

from vegapunk.embodied.safety import (
    ABORT_ENVELOPE_VIOLATION,
    ABORT_HUMAN_STOP,
    ABORT_OBSERVATION_STALE,
    ABORT_TIME_LIMIT,
    Observation,
    SafetyEnvelope,
    SafetySupervisor,
)

_ENVELOPE = SafetyEnvelope(
    max_duration_s=10.0,
    max_joint_velocity_rps=1.5,
    max_end_effector_force_n=20.0,
    workspace_bounds_m=((-0.5, 0.5), (-0.4, 0.4), (0.0, 1.2)),
    max_observation_age_s=0.2,
)


def _observation(**overrides: object) -> Observation:
    fields: dict[str, object] = {
        "elapsed_s": 1.0,
        "age_s": 0.05,
        "joint_velocity_rps": (0.0, 0.01),
        "end_effector_force_n": 2.0,
        "end_effector_position_m": (0.1, 0.0, 0.8),
        "guardian_present": True,
        "estop_engaged": False,
        "estop_reachable": True,
        "workspace_clear": True,
    }
    fields.update(overrides)
    return Observation(**fields)  # type: ignore[arg-type]


class PreflightTest(unittest.TestCase):
    def test_a_nominal_observation_passes_preflight(self) -> None:
        supervisor = SafetySupervisor(_ENVELOPE)

        result = supervisor.preflight(
            _observation(), required_preconditions=("workspace_clear",)
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.failures, ())

    def test_preflight_reports_every_failure_rather_than_the_first(
        self,
    ) -> None:
        supervisor = SafetySupervisor(_ENVELOPE)

        result = supervisor.preflight(
            _observation(
                guardian_present=False,
                estop_reachable=False,
                workspace_clear=False,
                end_effector_position_m=(0.9, 0.0, 0.8),
            ),
            required_preconditions=("workspace_clear",),
        )

        joined = " ".join(result.failures)
        self.assertFalse(result.passed)
        self.assertIn("guardian", joined)
        self.assertIn("estop", joined)
        self.assertIn("workspace_clear", joined)
        self.assertIn("workspace bounds", joined)

    def test_preflight_fails_when_the_robot_is_already_moving(self) -> None:
        supervisor = SafetySupervisor(_ENVELOPE)

        result = supervisor.preflight(
            _observation(joint_velocity_rps=(0.0, 0.9)),
            required_preconditions=(),
        )

        self.assertFalse(result.passed)
        self.assertIn("at rest", " ".join(result.failures))

    def test_preflight_fails_on_a_stale_observation(self) -> None:
        supervisor = SafetySupervisor(_ENVELOPE)

        result = supervisor.preflight(
            _observation(age_s=5.0), required_preconditions=()
        )

        self.assertFalse(result.passed)
        self.assertIn("stale", " ".join(result.failures))

    def test_preflight_fails_when_a_precondition_is_unknown_to_the_sensors(
        self,
    ) -> None:
        supervisor = SafetySupervisor(_ENVELOPE)

        result = supervisor.preflight(
            _observation(), required_preconditions=("gripper_calibrated",)
        )

        self.assertFalse(result.passed)
        self.assertIn("gripper_calibrated", " ".join(result.failures))

    def test_preflight_is_deterministic_for_the_same_observation(self) -> None:
        supervisor = SafetySupervisor(_ENVELOPE)
        observation = _observation(end_effector_force_n=99.0)

        first = supervisor.preflight(observation, required_preconditions=())
        second = supervisor.preflight(observation, required_preconditions=())

        self.assertEqual(first.failures, second.failures)


class RuntimeAbortTest(unittest.TestCase):
    def test_a_nominal_observation_does_not_abort(self) -> None:
        supervisor = SafetySupervisor(_ENVELOPE)

        self.assertIsNone(supervisor.evaluate(_observation()))

    def test_a_human_stop_aborts_immediately(self) -> None:
        supervisor = SafetySupervisor(_ENVELOPE)

        directive = supervisor.evaluate(_observation(estop_engaged=True))

        self.assertIsNotNone(directive)
        assert directive is not None
        self.assertEqual(directive.cause, ABORT_HUMAN_STOP)

    def test_a_departed_guardian_aborts(self) -> None:
        supervisor = SafetySupervisor(_ENVELOPE)

        directive = supervisor.evaluate(_observation(guardian_present=False))

        assert directive is not None
        self.assertEqual(directive.cause, ABORT_HUMAN_STOP)

    def test_exceeding_the_force_limit_aborts_with_the_measured_value(
        self,
    ) -> None:
        supervisor = SafetySupervisor(_ENVELOPE)

        directive = supervisor.evaluate(
            _observation(end_effector_force_n=25.0)
        )

        assert directive is not None
        self.assertEqual(directive.cause, ABORT_ENVELOPE_VIOLATION)
        self.assertIn("25.0", directive.detail)

    def test_exceeding_the_velocity_limit_aborts(self) -> None:
        supervisor = SafetySupervisor(_ENVELOPE)

        directive = supervisor.evaluate(
            _observation(joint_velocity_rps=(0.1, 2.0))
        )

        assert directive is not None
        self.assertEqual(directive.cause, ABORT_ENVELOPE_VIOLATION)

    def test_leaving_the_workspace_aborts(self) -> None:
        supervisor = SafetySupervisor(_ENVELOPE)

        directive = supervisor.evaluate(
            _observation(end_effector_position_m=(0.0, 0.0, 1.9))
        )

        assert directive is not None
        self.assertEqual(directive.cause, ABORT_ENVELOPE_VIOLATION)

    def test_exceeding_the_time_limit_aborts(self) -> None:
        supervisor = SafetySupervisor(_ENVELOPE)

        directive = supervisor.evaluate(_observation(elapsed_s=11.0))

        assert directive is not None
        self.assertEqual(directive.cause, ABORT_TIME_LIMIT)

    def test_a_stale_observation_aborts_rather_than_assuming_continuity(
        self,
    ) -> None:
        supervisor = SafetySupervisor(_ENVELOPE)

        directive = supervisor.evaluate(_observation(age_s=0.9))

        assert directive is not None
        self.assertEqual(directive.cause, ABORT_OBSERVATION_STALE)

    def test_a_human_stop_outranks_a_concurrent_envelope_violation(
        self,
    ) -> None:
        supervisor = SafetySupervisor(_ENVELOPE)

        directive = supervisor.evaluate(
            _observation(estop_engaged=True, end_effector_force_n=99.0)
        )

        assert directive is not None
        self.assertEqual(directive.cause, ABORT_HUMAN_STOP)


class SupervisorAuthorityTest(unittest.TestCase):
    def test_the_envelope_cannot_be_widened_after_construction(self) -> None:
        supervisor = SafetySupervisor(_ENVELOPE)

        with self.assertRaises(Exception):
            supervisor.envelope.max_end_effector_force_n = 999.0  # type: ignore[misc]

    def test_advisory_input_cannot_relax_a_limit(self) -> None:
        supervisor = SafetySupervisor(_ENVELOPE)

        tightened = supervisor.with_advice(
            {"max_end_effector_force_n": 10.0, "max_duration_s": 5.0}
        )
        with self.assertRaises(ValueError) as caught:
            supervisor.with_advice({"max_end_effector_force_n": 40.0})

        self.assertEqual(tightened.envelope.max_end_effector_force_n, 10.0)
        self.assertEqual(supervisor.envelope.max_end_effector_force_n, 20.0)
        self.assertIn("relax", str(caught.exception))

    def test_advisory_input_cannot_introduce_unknown_limits(self) -> None:
        supervisor = SafetySupervisor(_ENVELOPE)

        with self.assertRaises(ValueError):
            supervisor.with_advice({"ignore_estop": True})

    def test_an_envelope_requires_positive_limits(self) -> None:
        with self.assertRaises(ValueError):
            SafetyEnvelope(
                max_duration_s=0.0,
                max_joint_velocity_rps=1.5,
                max_end_effector_force_n=20.0,
                workspace_bounds_m=((-0.5, 0.5), (-0.4, 0.4), (0.0, 1.2)),
            )

    def test_an_envelope_requires_ordered_workspace_bounds(self) -> None:
        with self.assertRaises(ValueError):
            SafetyEnvelope(
                max_duration_s=10.0,
                max_joint_velocity_rps=1.5,
                max_end_effector_force_n=20.0,
                workspace_bounds_m=((0.5, -0.5), (-0.4, 0.4), (0.0, 1.2)),
            )


if __name__ == "__main__":
    unittest.main()
