from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from unittest.mock import patch

from vegapunk.embodied.observation_shadow import (
    COMPLIANT_OUTPUT,
    INFERENCE_FAILURE,
    INVALID_TARGET,
    PROJECTION,
    STALE_INTENT,
    STARVATION,
    CandidateOutput,
    ObservationShadow,
    ShadowEvidenceLedger,
)
from vegapunk.embodied.promotion import CandidateBundle
from vegapunk.operation.policy import Observation
from vegapunk.operation.target import HAND_OPEN, STAND_BODY, WholeBodyTarget
from vegapunk.operation.tracker import TrackerState

NOW_NS = 2_000_000_000
AT = datetime(2026, 8, 21, 16, 0, tzinfo=timezone.utc)
OBSERVATION_SCHEMA = "observation-schema-001"
POLICY_ARTIFACT = "policy-artifact-001"


def _observation() -> Observation:
    return Observation(
        time_ns=NOW_NS,
        images={"head": object()},
        state=TrackerState(
            sequence=5,
            state_time_ns=NOW_NS,
            body=(0.0,) * 34,
            left_hand=HAND_OPEN,
            right_hand=HAND_OPEN,
            applied_target_sequence=4,
        ),
    )


def _candidate() -> CandidateBundle:
    return CandidateBundle(
        candidate_id="candidate-shadow-001",
        policy_artifact_digest=POLICY_ARTIFACT,
        data_manifest_digest="training-manifest-001",
        training_recipe_digest="recipe-001",
        observation_schema_digest=OBSERVATION_SCHEMA,
        action_schema_digest="whole-body-target-001",
        skill_revision_id="golden-instrument-operation-loop@1",
        skill_revision_digest="skill-revision-001",
        embodiment_digest="embodiment-001",
        configuration_digest="configuration-001",
    )


def _output(
    sequence: int = 1,
    *,
    body: tuple[float, ...] = STAND_BODY,
    intent_produced_at_ns: int | None = None,
) -> CandidateOutput:
    return CandidateOutput(
        sequence=sequence,
        source_time_ns=NOW_NS,
        valid_until_ns=NOW_NS + 60_000_000,
        body=body,
        left_hand=HAND_OPEN,
        right_hand=HAND_OPEN,
        intent_produced_at_ns=intent_produced_at_ns,
    )


@dataclass
class _Runtime:
    output: CandidateOutput | WholeBodyTarget | None
    policy_artifact_digest: str = POLICY_ARTIFACT
    observation_schema_digest: str = OBSERVATION_SCHEMA
    action_schema_digest: str = "whole-body-target-001"
    seen: Observation | None = None

    def infer(
        self, observation: Observation
    ) -> CandidateOutput | WholeBodyTarget | None:
        self.seen = observation
        return self.output


class _FailingRuntime(_Runtime):
    def infer(
        self, observation: Observation
    ) -> CandidateOutput | WholeBodyTarget | None:
        self.seen = observation
        raise RuntimeError("candidate checkpoint unavailable")


class ObservationShadowAcceptanceTest(unittest.TestCase):
    def _shadow(self, runtime: _Runtime) -> ObservationShadow:
        return ObservationShadow(
            candidate=_candidate(),
            runtime=runtime,
            ledger=ShadowEvidenceLedger(),
        )

    def test_real_observation_and_candidate_artifact_produce_evidence_not_motion(
        self,
    ) -> None:
        moving = list(STAND_BODY)
        moving[0] = 0.4
        runtime = _Runtime(_output(body=tuple(moving)))
        shadow = self._shadow(runtime)
        observation = _observation()

        with (
            patch(
                "vegapunk.operation.bridge.TargetBridge.publish", autospec=True
            ) as publish,
            patch("vegapunk.operation.bridge.TargetBridge.hold", autospec=True) as hold,
        ):
            attempt = shadow.run(observation)

        publish.assert_not_called()
        hold.assert_not_called()
        evidence = shadow.seal(AT)

        self.assertIs(runtime.seen, observation)
        self.assertEqual(attempt.outcome, COMPLIANT_OUTPUT)
        self.assertIsNotNone(attempt.target)
        assert attempt.target is not None
        self.assertEqual(attempt.target.root_velocity_mps, (0.4, 0.0))
        self.assertEqual(evidence.candidate_digest, _candidate().digest())
        self.assertEqual(evidence.policy_artifact_digest, POLICY_ARTIFACT)
        self.assertEqual(evidence.observation_schema_digest, OBSERVATION_SCHEMA)
        self.assertEqual(
            evidence.conclusion,
            "compliant candidate output on real observations; does not prove task execution success",
        )
        self.assertEqual(evidence.perception_distribution.image_streams, ("head",))
        self.assertEqual(evidence.perception_distribution.distinct_image_references, 1)

    def test_shadow_keeps_every_required_failure_as_evidence(self) -> None:
        stale_output = _output(intent_produced_at_ns=NOW_NS - 1_000_000_001)
        invalid_output = _output(body=STAND_BODY[:-1])
        projected_body = list(STAND_BODY)
        projected_body[0] = 2.0
        cases = (
            (_FailingRuntime(None), INFERENCE_FAILURE),
            (_Runtime(None), STARVATION),
            (_Runtime(stale_output), STALE_INTENT),
            (_Runtime(invalid_output), INVALID_TARGET),
            (_Runtime(_output(body=tuple(projected_body))), PROJECTION),
        )

        for runtime, expected in cases:
            with self.subTest(expected=expected):
                shadow = self._shadow(runtime)
                attempt = shadow.run(_observation())
                evidence = shadow.seal(AT)

                self.assertEqual(attempt.outcome, expected)
                self.assertEqual(evidence.attempts, (attempt,))

    def test_deployment_ordering_and_expiry_are_checked_without_a_bridge(self) -> None:
        runtime = _Runtime(_output(sequence=1))
        shadow = self._shadow(runtime)
        shadow.run(_observation())

        replayed = shadow.run(_observation())

        self.assertEqual(replayed.outcome, INVALID_TARGET)
        self.assertIn("not newer", replayed.detail)

        stale = CandidateOutput(
            sequence=2,
            source_time_ns=NOW_NS - 10,
            valid_until_ns=NOW_NS,
            body=STAND_BODY,
            left_hand=HAND_OPEN,
            right_hand=HAND_OPEN,
        )
        shadow = self._shadow(_Runtime(stale))
        self.assertEqual(shadow.run(_observation()).outcome, STALE_INTENT)

    def test_a_preprojected_whole_body_target_remains_projection_evidence(self) -> None:
        projected_body = list(STAND_BODY)
        projected_body[0] = 2.0
        materialized = WholeBodyTarget(
            sequence=1,
            source_time_ns=NOW_NS,
            valid_until_ns=NOW_NS + 60_000_000,
            body=tuple(projected_body),
            left_hand=HAND_OPEN,
            right_hand=HAND_OPEN,
        )

        attempt = self._shadow(_Runtime(materialized)).run(_observation())

        self.assertEqual(attempt.outcome, PROJECTION)
        self.assertIn("speed", attempt.detail)

    def test_runner_rejects_a_runtime_for_a_different_artifact_or_schema(self) -> None:
        with self.assertRaisesRegex(ValueError, "artifact"):
            self._shadow(_Runtime(_output(), policy_artifact_digest="other"))
        with self.assertRaisesRegex(ValueError, "observation schema"):
            self._shadow(_Runtime(_output(), observation_schema_digest="other"))
        with self.assertRaisesRegex(ValueError, "action schema"):
            self._shadow(_Runtime(_output(), action_schema_digest="other"))


if __name__ == "__main__":
    unittest.main()
