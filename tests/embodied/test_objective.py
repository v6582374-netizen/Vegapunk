"""What the objective refuses to reward, asserted rather than described.

The load-bearing test here is the ordering one: a candidate that is excellent
in one bucket and poor in another must score below a candidate that is
uniformly mediocre, even though the first has the better average. That
inequality is the entire anti-overfitting argument, so it is a test and not a
paragraph.

Every report in this file is a hand-built double. The objective consumes
recorded campaigns and nothing else, so a test that needed a simulator would be
testing a different contract than the one this module declares.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Optional, Sequence

from vegapunk.embodied.admission import (
    MINIMUM_STAGE_ATTEMPTS,
    STAGE_OFFLINE_REPLAY,
    EvidenceRecord,
)
from vegapunk.embodied.campaign import (
    HALTED_ABORTED,
    HALTED_COMPLETED,
    AttemptRecord,
    CampaignReport,
)
from vegapunk.embodied.fidelity import (
    FIDELITY_REPRESENTS,
    FidelityAssessment,
)
from vegapunk.embodied.objective import (
    DEFAULT_SENSITIVITY_PENALTY,
    DISQUALIFIED_SCORE,
    MINIMUM_BUCKET_ATTEMPTS,
    NOMINAL_BUCKET,
    BucketOutcome,
    CandidateScore,
    RobustnessObjective,
)
from vegapunk.embodied.trajectory import (
    OUTCOME_ABORTED,
    OUTCOME_FAILED_VERIFICATION,
    OUTCOME_REFUSED,
    OUTCOME_SUCCEEDED,
)
from vegapunk.mcts_node import MetricValue, WorstMetricValue

_NOW = datetime(2026, 8, 16, 9, 0, tzinfo=timezone.utc)

_DIGEST = "cand0000000000ab"


@dataclass(frozen=True)
class FakeRegimeSample:
    """Stands in for ``regime.RegimeSample``, which lands in parallel.

    Only the two members the objective's contract names are present: the axis
    values and a digest. Depending on more of the real type than the contract
    promises would couple this module's tests to a sibling's internals.
    """

    values: Mapping[str, float]

    def digest(self) -> str:
        return "sample" + "".join(
            f"{axis}{value:.3f}" for axis, value in sorted(self.values.items())
        )


@dataclass(frozen=True)
class SampledAttempt:
    """An ``AttemptRecord`` carrying the regime sample it was drawn from.

    The real ``AttemptVariation`` is gaining the optional ``sample`` field; the
    objective reads it defensively, so this double exercises the path that
    exists once it lands without waiting for it.
    """

    index: int
    run_id: str
    outcome: str
    variation_digest: str
    sample: Optional[FakeRegimeSample] = None
    findings: tuple[str, ...] = ()
    abort_cause: Optional[str] = None


def _evidence(
    attempts: int, successes: int, safety_violations: int = 0
) -> EvidenceRecord:
    return EvidenceRecord(
        stage=STAGE_OFFLINE_REPLAY,
        skill_version_id="home_arm@1",
        embodiment_digest="embodiment",
        policy_digest=None,
        attempts=attempts,
        successes=successes,
        safety_violations=safety_violations,
        recorded_at=_NOW,
    )


def _fidelity() -> FidelityAssessment:
    return FidelityAssessment(
        verdict=FIDELITY_REPRESENTS,
        environment_id="sim",
        environment_digest="environment",
        embodiment_digest="embodiment",
    )


def _report(
    attempts: Sequence[object],
    safety_violations: int = 0,
    halted: str = HALTED_COMPLETED,
) -> CampaignReport:
    executed = [
        record
        for record in attempts
        if getattr(record, "outcome") != OUTCOME_REFUSED
    ]
    successes = sum(
        1
        for record in executed
        if getattr(record, "outcome") == OUTCOME_SUCCEEDED
    )
    return CampaignReport(
        campaign_id="campaign",
        stage=STAGE_OFFLINE_REPLAY,
        scope=("home_arm@1", "embodiment", None),
        planned_attempts=len(attempts),
        attempts=tuple(attempts),  # type: ignore[arg-type]
        evidence=_evidence(len(executed), successes, safety_violations),
        fidelity=_fidelity(),
        halted=halted,
        halt_detail="",
        next_stage=None,
        next_stage_admitted=False,
    )


def _plain(count: int, successes: int, outcome=OUTCOME_FAILED_VERIFICATION):
    """``count`` attempts with no regime sample, ``successes`` of them good."""
    return [
        AttemptRecord(
            index=index,
            run_id=f"run-{index}",
            outcome=(
                OUTCOME_SUCCEEDED if index < successes else outcome
            ),
            variation_digest=f"var-{index}",
        )
        for index in range(count)
    ]


def _sampled(rows: Sequence[tuple[float, bool]], axis: str = "payload_kg"):
    """One attempt per (axis value, succeeded) pair."""
    return [
        SampledAttempt(
            index=index,
            run_id=f"run-{index}",
            outcome=(
                OUTCOME_SUCCEEDED
                if succeeded
                else OUTCOME_FAILED_VERIFICATION
            ),
            variation_digest=f"var-{index}",
            sample=FakeRegimeSample(values={axis: value}),
        )
        for index, (value, succeeded) in enumerate(rows)
    ]


class BucketOutcomeTests(unittest.TestCase):
    def test_a_bucket_reports_its_own_rate(self) -> None:
        bucket = BucketOutcome(label="payload_kg:low", attempts=4, successes=1)
        self.assertAlmostEqual(bucket.success_rate, 0.25)

    def test_an_empty_bucket_has_no_rate_rather_than_a_perfect_one(
        self,
    ) -> None:
        bucket = BucketOutcome(label=NOMINAL_BUCKET, attempts=0, successes=0)
        self.assertEqual(bucket.success_rate, 0.0)

    def test_a_bucket_cannot_record_more_successes_than_attempts(self) -> None:
        with self.assertRaises(ValueError) as caught:
            BucketOutcome(label="axis:high", attempts=2, successes=3)
        self.assertIn("3 successes", str(caught.exception))

    def test_a_bucket_requires_a_label(self) -> None:
        with self.assertRaises(ValueError):
            BucketOutcome(label="", attempts=1, successes=1)


class DisqualificationTests(unittest.TestCase):
    """A broken envelope is not a lower score. It is not a candidate."""

    def test_a_safety_violation_disqualifies_the_candidate(self) -> None:
        report = _report(_plain(12, 12), safety_violations=1)
        score = RobustnessObjective().score(_DIGEST, [report])
        self.assertEqual(score.score, DISQUALIFIED_SCORE)
        self.assertTrue(score.disqualified)
        self.assertIsInstance(score.as_metric(), WorstMetricValue)
        self.assertTrue(score.as_metric().is_worst)
        self.assertTrue(
            any("safety violation" in note for note in score.findings)
        )

    def test_a_perfect_but_unsafe_candidate_loses_to_a_poor_safe_one(
        self,
    ) -> None:
        unsafe = RobustnessObjective().score(
            _DIGEST, [_report(_plain(12, 12), safety_violations=1)]
        )
        barely = RobustnessObjective().score(
            "other", [_report(_plain(12, 1))]
        )
        self.assertTrue(barely.as_metric() > unsafe.as_metric())

    def test_an_abort_disqualifies_the_candidate(self) -> None:
        attempts = _plain(11, 11) + [
            AttemptRecord(
                index=11,
                run_id="run-11",
                outcome=OUTCOME_ABORTED,
                variation_digest="var-11",
                abort_cause="envelope_violation",
            )
        ]
        score = RobustnessObjective().score(
            _DIGEST, [_report(attempts, halted=HALTED_ABORTED)]
        )
        self.assertTrue(score.aborted)
        self.assertEqual(score.score, DISQUALIFIED_SCORE)
        self.assertIsInstance(score.as_metric(), WorstMetricValue)

    def test_a_halted_campaign_is_an_abort_even_without_an_aborted_record(
        self,
    ) -> None:
        # The ledger's halt reason is authority in its own right: the abort may
        # have landed on a run this report does not enumerate.
        score = RobustnessObjective().score(
            _DIGEST, [_report(_plain(12, 12), halted=HALTED_ABORTED)]
        )
        self.assertTrue(score.aborted)
        self.assertTrue(score.disqualified)

    def test_too_few_attempts_disqualifies_the_candidate(self) -> None:
        score = RobustnessObjective().score(_DIGEST, [_report(_plain(3, 3))])
        self.assertEqual(score.attempts, 3)
        self.assertEqual(score.score, DISQUALIFIED_SCORE)
        self.assertIsInstance(score.as_metric(), WorstMetricValue)
        self.assertTrue(
            any("below the" in note for note in score.findings)
        )

    def test_an_under_measured_candidate_cannot_outrank_a_measured_one(
        self,
    ) -> None:
        lucky = RobustnessObjective().score(_DIGEST, [_report(_plain(2, 2))])
        measured = RobustnessObjective().score(
            "other", [_report(_plain(12, 6))]
        )
        self.assertTrue(measured.as_metric() > lucky.as_metric())

    def test_a_refusal_is_not_an_attempt(self) -> None:
        # A refusal says the configuration could not run at all, so counting it
        # as a failure would score admissibility as performance.
        attempts = _plain(12, 12) + [
            AttemptRecord(
                index=12,
                run_id="run-12",
                outcome=OUTCOME_REFUSED,
                variation_digest="var-12",
            )
        ]
        score = RobustnessObjective().score(_DIGEST, [_report(attempts)])
        self.assertEqual(score.attempts, 12)
        self.assertAlmostEqual(score.regime_success_rate, 1.0)

    def test_no_reports_at_all_is_disqualified_not_zero(self) -> None:
        score = RobustnessObjective().score(_DIGEST, [])
        self.assertEqual(score.attempts, 0)
        self.assertTrue(score.disqualified)
        self.assertIsNone(score.worst_bucket)

    def test_the_minimum_is_configurable_but_never_zero(self) -> None:
        objective = RobustnessObjective(minimum_attempts=2)
        score = objective.score(_DIGEST, [_report(_plain(2, 1))])
        self.assertFalse(score.disqualified)
        with self.assertRaises(ValueError) as caught:
            RobustnessObjective(minimum_attempts=0)
        self.assertIn("never ran", str(caught.exception))

    def test_a_negative_penalty_is_refused(self) -> None:
        with self.assertRaises(ValueError) as caught:
            RobustnessObjective(sensitivity_penalty=-0.1)
        self.assertIn("brittle", str(caught.exception))


class ScoreArithmeticTests(unittest.TestCase):
    def test_the_score_is_the_rate_less_the_penalised_sensitivity(
        self,
    ) -> None:
        # Six low-side attempts at 1/3, six high-side at 1: regime 2/3, worst
        # bucket 1/3, so sensitivity is 1/3.
        rows = [(0.0, False), (0.1, False), (0.2, True)] * 2
        rows += [(1.0, True), (1.1, True), (1.2, True)] * 2
        objective = RobustnessObjective(sensitivity_penalty=0.5)
        score = objective.score(_DIGEST, [_report(_sampled(rows))])

        self.assertEqual(score.attempts, 12)
        self.assertAlmostEqual(score.regime_success_rate, 8 / 12)
        self.assertIsNotNone(score.worst_bucket)
        assert score.worst_bucket is not None
        self.assertAlmostEqual(score.worst_bucket.success_rate, 1 / 3)
        self.assertAlmostEqual(score.sensitivity, 8 / 12 - 1 / 3)
        self.assertAlmostEqual(
            score.score, 8 / 12 - 0.5 * (8 / 12 - 1 / 3)
        )

    def test_a_uniform_candidate_pays_no_sensitivity(self) -> None:
        rows = [(0.0, True), (0.1, False), (1.0, True), (1.1, False)] * 3
        score = RobustnessObjective().score(_DIGEST, [_report(_sampled(rows))])
        self.assertAlmostEqual(score.sensitivity, 0.0)
        self.assertAlmostEqual(score.score, score.regime_success_rate)

    def test_sensitivity_never_goes_negative(self) -> None:
        # A worst bucket above the regime rate is arithmetically impossible,
        # but a floor of zero means no bucketing quirk can ever pay a bonus.
        score = RobustnessObjective().score(
            _DIGEST, [_report(_plain(12, 12))]
        )
        self.assertGreaterEqual(score.sensitivity, 0.0)

    def test_a_valid_score_is_a_maximising_metric(self) -> None:
        score = RobustnessObjective().score(_DIGEST, [_report(_plain(12, 9))])
        metric = score.as_metric()
        self.assertIsInstance(metric, MetricValue)
        self.assertFalse(metric.is_worst)
        self.assertTrue(metric.maximize)
        self.assertAlmostEqual(float(metric.value or 0.0), score.score)


class AntiOverfittingOrderingTests(unittest.TestCase):
    """The property that stops the search from winning one corner.

    A candidate that is excellent in one bucket and poor in another has the
    better average here, and must still lose. If this test ever passes only
    because of the averages, the objective has stopped doing its job.
    """

    def test_a_lopsided_candidate_scores_below_a_uniform_one(self) -> None:
        objective = RobustnessObjective()

        # 100% in the high bucket, 20% in the low one: average 60%.
        lopsided_rows = [
            (0.0, True),
            (0.0, False),
            (0.0, False),
            (0.0, False),
            (0.0, False),
            (1.0, True),
            (1.0, True),
            (1.0, True),
            (1.0, True),
            (1.0, True),
        ]
        lopsided = objective.score(
            "lopsided", [_report(_sampled(lopsided_rows))]
        )

        # 70% on both sides: a worse average, a better candidate.
        uniform_rows = [
            (0.0, True),
            (0.0, True),
            (0.0, True),
            (0.0, True),
            (0.0, True),
            (0.0, True),
            (0.0, True),
            (0.0, False),
            (0.0, False),
            (0.0, False),
            (1.0, True),
            (1.0, True),
            (1.0, True),
            (1.0, True),
            (1.0, True),
            (1.0, True),
            (1.0, True),
            (1.0, False),
            (1.0, False),
            (1.0, False),
        ]
        uniform = objective.score("uniform", [_report(_sampled(uniform_rows))])

        self.assertAlmostEqual(lopsided.regime_success_rate, 0.6)
        self.assertAlmostEqual(uniform.regime_success_rate, 0.7)
        self.assertAlmostEqual(uniform.sensitivity, 0.0)
        self.assertLess(lopsided.score, uniform.score)
        self.assertTrue(uniform.as_metric() > lopsided.as_metric())

    def test_a_lopsided_candidate_loses_even_with_the_better_average(
        self,
    ) -> None:
        objective = RobustnessObjective()

        # 100%/20% again, but padded until the average beats the uniform rival.
        lopsided_rows = [(0.0, index < 2) for index in range(10)]
        lopsided_rows += [(1.0, True)] * 20
        lopsided = objective.score(
            "lopsided", [_report(_sampled(lopsided_rows))]
        )
        uniform_rows = [(0.0, index < 7) for index in range(10)]
        uniform_rows += [(1.0, index < 7) for index in range(10)]
        uniform = objective.score("uniform", [_report(_sampled(uniform_rows))])

        self.assertGreater(
            lopsided.regime_success_rate, uniform.regime_success_rate
        )
        self.assertLess(lopsided.score, uniform.score)

    def test_the_default_penalty_makes_specialising_a_losing_trade(
        self,
    ) -> None:
        # Above 0.5 the search cannot profit by trading worst-bucket rate for
        # an equal gain elsewhere. That is why the default is 0.75.
        self.assertGreater(DEFAULT_SENSITIVITY_PENALTY, 0.5)
        self.assertLess(DEFAULT_SENSITIVITY_PENALTY, 1.0)

        objective = RobustnessObjective()
        balanced = objective.score(
            "balanced",
            [_report(_sampled([(0.0, index < 6) for index in range(10)]
                              + [(1.0, index < 6) for index in range(10)]))],
        )
        traded = objective.score(
            "traded",
            [_report(_sampled([(0.0, index < 4) for index in range(10)]
                              + [(1.0, index < 8) for index in range(10)]))],
        )
        self.assertAlmostEqual(
            balanced.regime_success_rate, traded.regime_success_rate
        )
        self.assertLess(traded.score, balanced.score)


class BucketingTests(unittest.TestCase):
    def test_attempts_without_a_sample_fall_into_one_nominal_bucket(
        self,
    ) -> None:
        score = RobustnessObjective().score(_DIGEST, [_report(_plain(12, 6))])
        self.assertIsNotNone(score.worst_bucket)
        assert score.worst_bucket is not None
        self.assertEqual(score.worst_bucket.label, NOMINAL_BUCKET)
        self.assertEqual(score.worst_bucket.attempts, 12)
        # One bucket cannot differ from itself, so nothing is penalised.
        self.assertAlmostEqual(score.sensitivity, 0.0)

    def test_each_axis_splits_at_the_midpoint_of_what_was_sampled(
        self,
    ) -> None:
        # Values 0.0 .. 1.0 put the midpoint at 0.5 regardless of any declared
        # bound the campaign never approached.
        rows = [(0.0, False), (0.2, False), (0.8, True), (1.0, True)] * 3
        score = RobustnessObjective().score(_DIGEST, [_report(_sampled(rows))])
        assert score.worst_bucket is not None
        self.assertEqual(score.worst_bucket.label, "payload_kg:low")
        self.assertEqual(score.worst_bucket.attempts, 6)
        self.assertAlmostEqual(score.worst_bucket.success_rate, 0.0)

    def test_buckets_are_labelled_by_axis_and_side(self) -> None:
        rows = [(0.0, True), (1.0, False)] * 6
        score = RobustnessObjective().score(
            _DIGEST, [_report(_sampled(rows, axis="friction"))]
        )
        assert score.worst_bucket is not None
        self.assertEqual(score.worst_bucket.label, "friction:high")

    def test_every_axis_is_bucketed_not_only_the_first(self) -> None:
        rows = []
        for index in range(12):
            # Payload is uniformly survivable; friction is not, and only a
            # per-axis split can see it.
            friction = 0.0 if index % 2 else 1.0
            rows.append(
                SampledAttempt(
                    index=index,
                    run_id=f"run-{index}",
                    outcome=(
                        OUTCOME_SUCCEEDED
                        if friction == 0.0
                        else OUTCOME_FAILED_VERIFICATION
                    ),
                    variation_digest=f"var-{index}",
                    sample=FakeRegimeSample(
                        values={
                            "payload_kg": float(index % 3),
                            "friction": friction,
                        }
                    ),
                )
            )
        score = RobustnessObjective().score(_DIGEST, [_report(rows)])
        assert score.worst_bucket is not None
        self.assertEqual(score.worst_bucket.label, "friction:high")
        self.assertAlmostEqual(score.worst_bucket.success_rate, 0.0)

    def test_a_thinly_sampled_bucket_cannot_define_the_worst_case(
        self,
    ) -> None:
        # One attempt is a coin flip, not a rate. Eleven good runs plus a
        # single unlucky outlier must not be scored as total brittleness.
        rows = [(0.5, True)] * 11 + [(1.0, False)]
        score = RobustnessObjective().score(_DIGEST, [_report(_sampled(rows))])
        assert score.worst_bucket is not None
        self.assertGreaterEqual(
            score.worst_bucket.attempts, MINIMUM_BUCKET_ATTEMPTS
        )
        self.assertNotEqual(score.worst_bucket.attempts, 1)

    def test_unsampled_attempts_are_pooled_and_declared(self) -> None:
        rows = list(_sampled([(0.0, True), (1.0, False)] * 5))
        rows += _plain(2, 0)  # type: ignore[arg-type]
        score = RobustnessObjective().score(_DIGEST, [_report(rows)])
        self.assertTrue(
            any("no regime sample" in note for note in score.findings)
        )

    def test_reports_accumulate_across_campaigns(self) -> None:
        first = _report(_sampled([(0.0, False)] * 6))
        second = _report(_sampled([(1.0, True)] * 6))
        score = RobustnessObjective().score(_DIGEST, [first, second])
        self.assertEqual(score.attempts, 12)
        self.assertEqual(score.successes, 6)


class LedgerAuthorityTests(unittest.TestCase):
    """The recorded runs are the authority; the scorer does not recount."""

    def test_safety_violations_come_from_the_evidence_not_the_outcomes(
        self,
    ) -> None:
        # Every attempt reads as a plain verification failure. Only the
        # ledger's evidence knows an envelope was broken, and that is enough.
        report = _report(_plain(12, 8), safety_violations=2)
        score = RobustnessObjective().score(_DIGEST, [report])
        self.assertEqual(score.safety_violations, 2)
        self.assertTrue(score.disqualified)

    def test_successes_are_read_from_the_attempt_outcomes(self) -> None:
        score = RobustnessObjective().score(_DIGEST, [_report(_plain(12, 5))])
        self.assertEqual(score.successes, 5)
        self.assertAlmostEqual(score.regime_success_rate, 5 / 12)

    def test_the_candidate_digest_is_carried_through_verbatim(self) -> None:
        score = RobustnessObjective().score(
            "attributed-digest", [_report(_plain(12, 12))]
        )
        self.assertEqual(score.candidate_digest, "attributed-digest")


class CandidateScoreRecordTests(unittest.TestCase):
    def test_the_digest_covers_the_score_and_its_evidence(self) -> None:
        objective = RobustnessObjective()
        first = objective.score(_DIGEST, [_report(_plain(12, 6))])
        same = objective.score(_DIGEST, [_report(_plain(12, 6))])
        different = objective.score(_DIGEST, [_report(_plain(12, 7))])
        self.assertEqual(first.digest(), same.digest())
        self.assertNotEqual(first.digest(), different.digest())

    def test_a_disqualified_score_digests_without_an_infinity(self) -> None:
        # ``-inf`` is not valid JSON, so a disqualified score has to be
        # recordable as a word rather than as a number.
        score = RobustnessObjective().score(_DIGEST, [_report(_plain(1, 1))])
        self.assertTrue(score.disqualified)
        self.assertRegex(score.digest(), r"^[0-9a-f]{16}$")

    def test_findings_are_a_tuple_whatever_they_were_built_from(self) -> None:
        score = CandidateScore(
            candidate_digest=_DIGEST,
            attempts=12,
            successes=6,
            regime_success_rate=0.5,
            worst_bucket=None,
            sensitivity=0.0,
            safety_violations=0,
            aborted=False,
            score=0.5,
            findings=["one"],  # type: ignore[arg-type]
        )
        self.assertEqual(score.findings, ("one",))

    def test_the_default_minimum_matches_the_admission_ladder(self) -> None:
        # A candidate measured on less than a stage's worth of attempts is not
        # measured; borrowing the ladder's number keeps one definition of that.
        self.assertEqual(
            RobustnessObjective().minimum_attempts, MINIMUM_STAGE_ATTEMPTS
        )


if __name__ == "__main__":
    unittest.main()
