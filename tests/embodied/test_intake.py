"""What a complaint in prose is allowed to authorise, and what it is not."""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timezone
from typing import Mapping, Optional

from vegapunk.embodied.intake import (
    ADAPTATION_PATH_ORDER,
    AUTOMATABLE_PATHS,
    PATH_ENVIRONMENT,
    PATH_FINETUNE,
    PATH_INSTRUCTION,
    PATH_INTERFACE,
    PATH_RESIDUAL,
    PROMPT_TRIAGE,
    SYMPTOM_COMPETENT_BUT_WRONG,
    SYMPTOM_ERRATIC_OR_INERT,
    SYMPTOM_SCENE_SENSITIVE,
    SYMPTOM_SYSTEMATIC_OFFSET,
    SYMPTOM_UNCLASSIFIABLE,
    AdaptationBrief,
    PainPoint,
    brief_from_classification,
    physical_claims,
    triage,
)
from vegapunk.prompt_library import get_prompt_library

NOW = datetime(2026, 8, 16, 9, 0, tzinfo=timezone.utc)


def _pain_point(**overrides: object) -> PainPoint:
    fields: dict[str, object] = {
        "text": "The arm lurches when I ask it to pick up the red block.",
        "submitted_by": "operator",
        "submitted_at": NOW,
    }
    fields.update(overrides)
    return PainPoint(**fields)


def _classification(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "symptom": SYMPTOM_ERRATIC_OR_INERT,
        "routed_path": PATH_INTERFACE,
        "objective_statement": (
            "Show that the commanded motion is smooth and completes the "
            "requested pick without lurching."
        ),
        "observable_success": (
            "the run reaches its terminal postcondition",
            "no abort is raised during the run",
        ),
        "unknowns": ("which joints the policy is actually commanding",),
        "rejected_paths": (
            {"path": PATH_ENVIRONMENT, "reason": "the scene is nominal"},
        ),
    }
    fields.update(overrides)
    return fields


class FakeRuntime:
    """An async JSON seam whose reply is decided by the test, not a model."""

    def __init__(
        self,
        reply: object = None,
        error: Optional[Exception] = None,
    ) -> None:
        self._reply = reply
        self._error = error
        self.calls: list[dict[str, object]] = []

    async def generate_json(
        self,
        prompt: str,
        *,
        schema: Optional[Mapping[str, object]] = None,
        system_prompt: Optional[str] = None,
        model_id: Optional[str] = None,
        reasoning: object = None,
    ) -> dict[str, object]:
        self.calls.append(
            {"prompt": prompt, "schema": schema, "model_id": model_id}
        )
        if self._error is not None:
            raise self._error
        return self._reply  # type: ignore[return-value]


class LadderTests(unittest.TestCase):
    """The ladder is the module's claim, so its shape is asserted."""

    def test_the_ladder_runs_cheap_and_reversible_to_irreversible(
        self,
    ) -> None:
        self.assertEqual(
            ADAPTATION_PATH_ORDER,
            (
                PATH_ENVIRONMENT,
                PATH_INSTRUCTION,
                PATH_INTERFACE,
                PATH_RESIDUAL,
                PATH_FINETUNE,
            ),
        )

    def test_only_the_interface_layer_may_be_searched_unattended(self) -> None:
        self.assertEqual(AUTOMATABLE_PATHS, (PATH_INTERFACE,))
        for path in ADAPTATION_PATH_ORDER:
            if path != PATH_INTERFACE:
                self.assertNotIn(path, AUTOMATABLE_PATHS)


class ClassificationIsValidatedNotRepairedTests(unittest.TestCase):
    """Requirement 1: an unreadable classification is an error, never a
    default. A garbled reply that decayed into the searchable path would
    start a physical search on a semantic problem."""

    def test_a_well_formed_classification_becomes_a_brief(self) -> None:
        brief = brief_from_classification(_pain_point(), _classification())
        self.assertEqual(brief.symptom, SYMPTOM_ERRATIC_OR_INERT)
        self.assertEqual(brief.routed_path, PATH_INTERFACE)
        self.assertTrue(brief.searchable)
        self.assertEqual(brief.refusal, "")

    def test_an_unknown_symptom_is_refused_rather_than_defaulted(self) -> None:
        with self.assertRaises(ValueError):
            brief_from_classification(
                _pain_point(), _classification(symptom="jittery-ish")
            )

    def test_an_unknown_route_never_decays_to_the_searchable_path(
        self,
    ) -> None:
        with self.assertRaises(ValueError) as caught:
            brief_from_classification(
                _pain_point(),
                _classification(routed_path="interface_layer_probably"),
            )
        self.assertIn("not a route to the searchable path", str(
            caught.exception
        ))

    def test_a_missing_route_is_refused(self) -> None:
        payload = _classification()
        del payload["routed_path"]
        with self.assertRaises(ValueError):
            brief_from_classification(_pain_point(), payload)

    def test_a_missing_objective_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            brief_from_classification(
                _pain_point(), _classification(objective_statement="  ")
            )

    def test_a_rejected_path_off_the_ladder_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            brief_from_classification(
                _pain_point(),
                _classification(
                    rejected_paths=({"path": "vibes", "reason": "no"},)
                ),
            )

    def test_a_single_string_is_not_accepted_as_a_list_of_statements(
        self,
    ) -> None:
        # Would otherwise become a list of characters, silently.
        with self.assertRaises(ValueError):
            brief_from_classification(
                _pain_point(),
                _classification(observable_success="it works"),
            )

    def test_construction_is_the_only_way_to_hold_an_invalid_brief(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            AdaptationBrief(
                pain_point=_pain_point(),
                symptom="made_up",
                routed_path=PATH_INTERFACE,
                objective_statement="anything",
                observable_success=(),
                unknowns=(),
                rejected_paths=(),
                searchable=True,
            )


class RoutingRefusalTests(unittest.TestCase):
    """Requirement 2: anything off the automatable rung comes back refused,
    naming the path and the human act that must come first."""

    def test_every_non_automatable_path_is_unsearchable_and_says_why(
        self,
    ) -> None:
        for path in ADAPTATION_PATH_ORDER:
            if path in AUTOMATABLE_PATHS:
                continue
            with self.subTest(path=path):
                brief = brief_from_classification(
                    _pain_point(),
                    _classification(routed_path=path, rejected_paths=()),
                )
                self.assertFalse(brief.searchable)
                self.assertIn(path, brief.refusal)
                self.assertTrue(brief.refusal.strip())

    def test_the_environment_path_asks_a_person_to_change_the_scene(
        self,
    ) -> None:
        brief = brief_from_classification(
            _pain_point(),
            _classification(
                symptom=SYMPTOM_SCENE_SENSITIVE,
                routed_path=PATH_ENVIRONMENT,
                rejected_paths=(),
            ),
        )
        self.assertFalse(brief.searchable)
        self.assertIn("fixture", brief.refusal)

    def test_the_instruction_path_asks_a_person_to_restate_the_request(
        self,
    ) -> None:
        brief = brief_from_classification(
            _pain_point(),
            _classification(
                symptom=SYMPTOM_COMPETENT_BUT_WRONG,
                routed_path=PATH_INSTRUCTION,
                rejected_paths=(),
            ),
        )
        self.assertFalse(brief.searchable)
        self.assertIn("restate", brief.refusal)

    def test_the_residual_path_names_the_artifact_it_would_leave_behind(
        self,
    ) -> None:
        brief = brief_from_classification(
            _pain_point(),
            _classification(routed_path=PATH_RESIDUAL, rejected_paths=()),
        )
        self.assertFalse(brief.searchable)
        self.assertIn("corrector", brief.refusal)

    def test_finetune_states_both_the_checkpoint_and_the_data_harm(
        self,
    ) -> None:
        brief = brief_from_classification(
            _pain_point(),
            _classification(routed_path=PATH_FINETUNE, rejected_paths=()),
        )
        self.assertFalse(brief.searchable)
        refusal = brief.refusal
        self.assertIn(PATH_FINETUNE, refusal)
        self.assertIn("checkpoint", refusal)
        self.assertIn("contaminates", refusal)
        self.assertIn("verify the interface", refusal)

    def test_a_searchable_brief_cannot_also_carry_a_refusal(self) -> None:
        with self.assertRaises(ValueError):
            AdaptationBrief(
                pain_point=_pain_point(),
                symptom=SYMPTOM_SYSTEMATIC_OFFSET,
                routed_path=PATH_INTERFACE,
                objective_statement="anything",
                observable_success=(),
                unknowns=(),
                rejected_paths=(),
                searchable=True,
                refusal="but also no",
            )

    def test_an_unsearchable_brief_must_name_the_human_act(self) -> None:
        with self.assertRaises(ValueError):
            AdaptationBrief(
                pain_point=_pain_point(),
                symptom=SYMPTOM_SYSTEMATIC_OFFSET,
                routed_path=PATH_FINETUNE,
                objective_statement="anything",
                observable_success=(),
                unknowns=(),
                rejected_paths=(),
                searchable=False,
                refusal="",
            )

    def test_a_non_automatable_path_can_never_be_marked_searchable(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            AdaptationBrief(
                pain_point=_pain_point(),
                symptom=SYMPTOM_SYSTEMATIC_OFFSET,
                routed_path=PATH_FINETUNE,
                objective_statement="anything",
                observable_success=(),
                unknowns=(),
                rejected_paths=(),
                searchable=True,
            )


class NoPhysicalFactMayBeAssertedTests(unittest.TestCase):
    """Requirement 3: a guess about hardware becomes a question for a human,
    never a premise the campaign inherits."""

    def test_hardware_claims_are_recognised_by_class(self) -> None:
        self.assertIn(
            "end effector", physical_claims("the dex1 gripper is parallel")
        )
        self.assertIn(
            "control frequency", physical_claims("it runs the loop at 30 Hz")
        )
        self.assertIn(
            "degrees of freedom", physical_claims("the 7 DoF arm")
        )
        self.assertIn(
            "camera layout", physical_claims("the wrist camera is occluded")
        )
        self.assertEqual(physical_claims("the motion is not smooth"), ())

    def test_a_claimed_end_effector_is_relocated_to_unknowns(self) -> None:
        brief = brief_from_classification(
            _pain_point(),
            _classification(
                objective_statement=(
                    "Show the pick completes. The robot's parallel-jaw end "
                    "effector closes on the block."
                )
            ),
        )
        self.assertNotIn("end effector", brief.objective_statement)
        self.assertTrue(
            any("end effector" in unknown for unknown in brief.unknowns)
        )
        self.assertIn("Show the pick completes.", brief.objective_statement)

    def test_a_claimed_control_frequency_is_relocated_to_unknowns(
        self,
    ) -> None:
        brief = brief_from_classification(
            _pain_point(),
            _classification(
                objective_statement=(
                    "Demonstrate stable tracking. Commands are issued at "
                    "200 Hz to the arm."
                )
            ),
        )
        self.assertNotIn("200 Hz", brief.objective_statement)
        self.assertTrue(
            any("control frequency" in u for u in brief.unknowns)
        )

    def test_a_claimed_fact_in_observable_success_is_relocated_too(
        self,
    ) -> None:
        brief = brief_from_classification(
            _pain_point(),
            _classification(
                observable_success=(
                    "the run reaches its terminal postcondition",
                    "all 7 joints stay inside their limits",
                )
            ),
        )
        self.assertEqual(
            brief.observable_success,
            ("the run reaches its terminal postcondition",),
        )
        self.assertTrue(
            any("degrees of freedom" in u for u in brief.unknowns)
        )

    def test_an_objective_that_was_entirely_hardware_claims_is_replaced(
        self,
    ) -> None:
        brief = brief_from_classification(
            _pain_point(),
            _classification(
                objective_statement="The 7 DoF arm runs at 30 Hz."
            ),
        )
        self.assertTrue(brief.objective_statement.strip())
        self.assertEqual(physical_claims(brief.objective_statement), ())
        self.assertTrue(brief.unknowns)

    def test_a_brief_constructed_directly_may_not_assert_hardware_facts(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            AdaptationBrief(
                pain_point=_pain_point(),
                symptom=SYMPTOM_SYSTEMATIC_OFFSET,
                routed_path=PATH_INTERFACE,
                objective_statement="Command the 7 DoF arm correctly.",
                observable_success=(),
                unknowns=(),
                rejected_paths=(),
                searchable=True,
            )

    def test_unknowns_are_deduplicated_in_first_seen_order(self) -> None:
        brief = brief_from_classification(
            _pain_point(),
            _classification(
                unknowns=("which joints", "which joints", "which camera keys"),
            ),
        )
        self.assertEqual(
            brief.unknowns[:2], ("which joints", "which camera keys")
        )


class TriageSurvivesAnyReplyTests(unittest.TestCase):
    """Requirement 4: triage returns a brief for every reply, and a failure
    is visible as itself rather than as a routing decision."""

    def test_a_usable_reply_becomes_a_searchable_brief(self) -> None:
        runtime = FakeRuntime(reply=_classification())
        brief = asyncio.run(triage(_pain_point(), runtime))
        self.assertTrue(brief.searchable)
        self.assertEqual(brief.routed_path, PATH_INTERFACE)
        self.assertEqual(len(runtime.calls), 1)

    def test_the_prompt_comes_from_the_library_and_carries_the_complaint(
        self,
    ) -> None:
        runtime = FakeRuntime(reply=_classification())
        pain_point = _pain_point(text="It never moves at all.")
        asyncio.run(triage(pain_point, runtime))
        prompt = str(runtime.calls[0]["prompt"])
        self.assertIn("It never moves at all.", prompt)
        self.assertIn(PATH_FINETUNE, prompt)
        self.assertIn(SYMPTOM_ERRATIC_OR_INERT, prompt)

    def test_the_prompt_is_registered_on_disk_not_inlined(self) -> None:
        entry = get_prompt_library().get_entry(PROMPT_TRIAGE)
        self.assertEqual(entry.workflow, "embodied")
        text = get_prompt_library().get(PROMPT_TRIAGE)
        self.assertIn("unknowns", text)
        self.assertIn("{pain_point_text}", text)

    def test_a_malformed_reply_is_unclassifiable_and_unsearchable(
        self,
    ) -> None:
        runtime = FakeRuntime(reply={"symptom": "vibes", "routed_path": "eh"})
        brief = asyncio.run(triage(_pain_point(), runtime))
        self.assertEqual(brief.symptom, SYMPTOM_UNCLASSIFIABLE)
        self.assertFalse(brief.searchable)
        self.assertIn("vibes", brief.refusal)

    def test_a_non_object_reply_is_quoted_in_the_refusal(self) -> None:
        runtime = FakeRuntime(reply=["not", "an", "object"])
        brief = asyncio.run(triage(_pain_point(), runtime))
        self.assertEqual(brief.symptom, SYMPTOM_UNCLASSIFIABLE)
        self.assertIn("not", brief.refusal)

    def test_a_raising_runtime_does_not_raise_out_of_triage(self) -> None:
        runtime = FakeRuntime(error=RuntimeError("model unreachable"))
        brief = asyncio.run(triage(_pain_point(), runtime))
        self.assertEqual(brief.symptom, SYMPTOM_UNCLASSIFIABLE)
        self.assertFalse(brief.searchable)
        self.assertIn("model unreachable", brief.refusal)

    def test_an_unclassifiable_brief_is_never_routed_to_the_search(
        self,
    ) -> None:
        runtime = FakeRuntime(reply={})
        brief = asyncio.run(triage(_pain_point(), runtime))
        self.assertNotIn(brief.routed_path, AUTOMATABLE_PATHS)


class BriefIsATraceableRecordTests(unittest.TestCase):
    """A brief is the premise of everything downstream, so it must be
    identifiable and attributable."""

    def test_an_anonymous_complaint_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            _pain_point(submitted_by="   ")

    def test_an_empty_complaint_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            _pain_point(text="")

    def test_the_digest_changes_with_the_route(self) -> None:
        first = brief_from_classification(_pain_point(), _classification())
        second = brief_from_classification(
            _pain_point(),
            _classification(routed_path=PATH_FINETUNE, rejected_paths=()),
        )
        self.assertNotEqual(first.digest(), second.digest())

    def test_the_digest_is_stable_for_the_same_classification(self) -> None:
        first = brief_from_classification(_pain_point(), _classification())
        second = brief_from_classification(_pain_point(), _classification())
        self.assertEqual(first.digest(), second.digest())

    def test_the_contract_carries_the_refusal_and_the_submitter(self) -> None:
        brief = brief_from_classification(
            _pain_point(),
            _classification(routed_path=PATH_FINETUNE, rejected_paths=()),
        )
        contract = brief.as_contract()
        self.assertFalse(contract["searchable"])
        self.assertEqual(contract["submitted_by"], "operator")
        self.assertEqual(contract["routed_path"], PATH_FINETUNE)
        self.assertTrue(str(contract["refusal"]))
        self.assertEqual(contract["brief_digest"], brief.digest())

    def test_a_path_cannot_be_both_the_route_and_a_rejection(self) -> None:
        brief = brief_from_classification(
            _pain_point(),
            _classification(
                rejected_paths=(
                    {"path": PATH_INTERFACE, "reason": "contradictory"},
                    {"path": PATH_FINETUNE, "reason": "too expensive"},
                )
            ),
        )
        self.assertEqual(
            [path for path, _ in brief.rejected_paths], [PATH_FINETUNE]
        )


if __name__ == "__main__":
    unittest.main()
