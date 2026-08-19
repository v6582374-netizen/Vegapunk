from __future__ import annotations

import unittest

from vegapunk.operation.trace import (
    FACT_DEFINITE,
    FACT_INDETERMINATE,
    OUTCOME_FAILED,
    OUTCOME_INDETERMINATE,
    OUTCOME_SUCCEEDED,
    PREDICATE_CUP_LIFTED,
    PREDICATE_CUP_RETURNED,
    PREDICATE_CUP_TILTED,
    PREDICATE_FINAL_LID_CLOSED,
    PREDICATE_INITIAL_LID_CLOSED,
    PREDICATE_LID_OPENED,
    REQUIRED_TRACE,
    OperationTraceWitness,
    ResetVerdict,
    TraceFact,
    adjudicate,
)

_NOW = 1_700_000_000_000_000_000
_CHANNEL = "bench_camera"


def _fact(
    predicate: str,
    at: int,
    *,
    verdict: str = FACT_DEFINITE,
    fresh: bool = True,
) -> TraceFact:
    return TraceFact(
        predicate=predicate,
        verdict=verdict,
        channel=_CHANNEL,
        observed_at_ns=_NOW + at,
        fresh=fresh,
    )


def _full_trace() -> tuple[TraceFact, ...]:
    return tuple(
        _fact(predicate, index) for index, predicate in enumerate(REQUIRED_TRACE)
    )


def _reset(confirmed: bool = True) -> ResetVerdict:
    return ResetVerdict(
        confirmed=confirmed,
        channel=_CHANNEL,
        observed_at_ns=_NOW,
        detail="cup at home, lid closed" if confirmed else "cup pose unknown",
    )


class TraceFactTest(unittest.TestCase):
    def test_a_fact_names_its_channel(self) -> None:
        with self.assertRaises(ValueError):
            TraceFact(
                predicate=PREDICATE_LID_OPENED,
                verdict=FACT_DEFINITE,
                channel="  ",
                observed_at_ns=_NOW,
                fresh=True,
            )

    def test_a_fact_carries_no_probabilistic_confidence(self) -> None:
        # Confidence belongs to the predictive node, never to the adjudicator.
        fact = _fact(PREDICATE_LID_OPENED, 0)
        self.assertFalse(hasattr(fact, "confidence"))

    def test_a_verdict_is_definite_or_indeterminate_only(self) -> None:
        with self.assertRaises(ValueError):
            _fact(PREDICATE_LID_OPENED, 0, verdict="probably")


class TraceWitnessTest(unittest.TestCase):
    def test_the_trace_is_append_only_and_ordered(self) -> None:
        witness = OperationTraceWitness(identity=_CHANNEL)
        witness.observe(_fact(PREDICATE_INITIAL_LID_CLOSED, 0))
        witness.observe(_fact(PREDICATE_LID_OPENED, 10))

        self.assertEqual(
            [fact.predicate for fact in witness.trace],
            [PREDICATE_INITIAL_LID_CLOSED, PREDICATE_LID_OPENED],
        )
        with self.assertRaises(ValueError):
            witness.observe(_fact(PREDICATE_CUP_LIFTED, 5))  # time went backwards

    def test_the_witness_cannot_command_or_sequence(self) -> None:
        # Structural: observation is the only verb the witness has.
        witness = OperationTraceWitness(identity=_CHANNEL)
        for forbidden in ("command", "publish", "next_phase", "advance"):
            self.assertFalse(hasattr(witness, forbidden))


class AdjudicationTest(unittest.TestCase):
    def test_the_full_ordered_trace_with_a_confirmed_reset_succeeds(self) -> None:
        verdict = adjudicate(_full_trace(), reset=_reset())
        self.assertEqual(verdict.outcome, OUTCOME_SUCCEEDED)
        self.assertEqual(verdict.witnessed, REQUIRED_TRACE)

    def test_a_no_op_run_ending_with_a_closed_lid_fails(self) -> None:
        # The robot did nothing; the lid was closed at both ends. A terminal
        # closed lid is not a completed operation.
        trace = (
            _fact(PREDICATE_INITIAL_LID_CLOSED, 0),
            _fact(PREDICATE_FINAL_LID_CLOSED, 10),
        )
        verdict = adjudicate(trace, reset=_reset())
        self.assertEqual(verdict.outcome, OUTCOME_FAILED)
        self.assertIn(PREDICATE_LID_OPENED, verdict.detail)

    def test_an_unconfirmed_reset_is_never_a_success(self) -> None:
        verdict = adjudicate(_full_trace(), reset=_reset(confirmed=False))
        self.assertEqual(verdict.outcome, OUTCOME_INDETERMINATE)

    def test_a_stale_required_fact_cannot_be_promoted_to_success(self) -> None:
        facts = list(_full_trace())
        facts[2] = _fact(PREDICATE_CUP_LIFTED, 2, fresh=False)
        verdict = adjudicate(tuple(facts), reset=_reset())
        self.assertEqual(verdict.outcome, OUTCOME_INDETERMINATE)

    def test_an_indeterminate_required_fact_cannot_be_promoted(self) -> None:
        facts = list(_full_trace())
        facts[3] = _fact(PREDICATE_CUP_TILTED, 3, verdict=FACT_INDETERMINATE)
        verdict = adjudicate(tuple(facts), reset=_reset())
        self.assertEqual(verdict.outcome, OUTCOME_INDETERMINATE)

    def test_predicates_out_of_order_do_not_succeed(self) -> None:
        # The cup was seen lifted before the lid ever opened: whatever that
        # was, it was not the reversible operation.
        trace = (
            _fact(PREDICATE_INITIAL_LID_CLOSED, 0),
            _fact(PREDICATE_CUP_LIFTED, 1),
            _fact(PREDICATE_LID_OPENED, 2),
            _fact(PREDICATE_CUP_TILTED, 3),
            _fact(PREDICATE_CUP_RETURNED, 4),
            _fact(PREDICATE_FINAL_LID_CLOSED, 5),
        )
        verdict = adjudicate(trace, reset=_reset())
        self.assertNotEqual(verdict.outcome, OUTCOME_SUCCEEDED)

    def test_a_later_usable_fact_redeems_an_earlier_unusable_one(self) -> None:
        facts = list(_full_trace())
        facts.insert(
            2, _fact(PREDICATE_CUP_LIFTED, 1, verdict=FACT_INDETERMINATE)
        )
        verdict = adjudicate(tuple(facts), reset=_reset())
        self.assertEqual(verdict.outcome, OUTCOME_SUCCEEDED)

    def test_an_empty_trace_fails_rather_than_erring(self) -> None:
        verdict = adjudicate((), reset=_reset())
        self.assertEqual(verdict.outcome, OUTCOME_FAILED)


class ResetVerdictTest(unittest.TestCase):
    def test_a_witnessed_reset_is_distinguished_from_an_attested_one(self) -> None:
        witnessed = _reset()
        attested = ResetVerdict(
            confirmed=True,
            channel="human",
            observed_at_ns=_NOW,
            attested_by="Wei",
        )
        self.assertTrue(witnessed.witnessed)
        self.assertFalse(attested.witnessed)

    def test_a_reset_verdict_names_its_channel(self) -> None:
        with self.assertRaises(ValueError):
            ResetVerdict(confirmed=True, channel=" ", observed_at_ns=_NOW)


if __name__ == "__main__":
    unittest.main()
