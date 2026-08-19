from __future__ import annotations

import unittest

from vegapunk.embodied.embodiment import UNIFOLM_VLA_BASE_G1_EE6D
from vegapunk.embodied.skill import (
    SKILL_KIND_DETERMINISTIC,
    SKILL_KIND_VLA,
    ParameterSpec,
    PhysicalSkill,
    SkillRegistry,
    SkillSelection,
)


def _deterministic_skill(**overrides: object) -> PhysicalSkill:
    fields: dict[str, object] = {
        "skill_id": "press_physical_button",
        "revision": 1,
        "kind": SKILL_KIND_DETERMINISTIC,
        "summary": "Press one fixed laboratory button with the right gripper.",
        "parameters": (
            ParameterSpec(
                name="target_id",
                allowed_values=("bench_button_a", "bench_button_b"),
            ),
            ParameterSpec(
                name="approach_speed_mps",
                minimum=0.01,
                maximum=0.05,
            ),
        ),
        "preconditions": ("workspace_clear", "arms_at_home_pose"),
        "postconditions": ("button_depressed", "arms_at_home_pose"),
        "abort_conditions": ("force_limit_exceeded",),
        "max_duration_s": 12.0,
        "policy": None,
        "reviewed_by": "lab_owner",
    }
    fields.update(overrides)
    return PhysicalSkill(**fields)  # type: ignore[arg-type]


class SkillDefinitionTest(unittest.TestCase):
    def test_definition_identity_includes_its_revision(self) -> None:
        skill = _deterministic_skill()

        self.assertEqual(skill.version_id, "press_physical_button@1")
        self.assertNotEqual(
            skill.contract_digest(),
            _deterministic_skill(revision=2).contract_digest(),
        )

    def test_changing_any_contract_term_changes_the_digest(self) -> None:
        baseline = _deterministic_skill().contract_digest()

        self.assertNotEqual(
            baseline, _deterministic_skill(max_duration_s=30.0).contract_digest()
        )
        self.assertNotEqual(
            baseline,
            _deterministic_skill(postconditions=("button_depressed",)).contract_digest(),
        )

    def test_a_skill_without_verifiable_postconditions_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as caught:
            _deterministic_skill(postconditions=())

        self.assertIn("postcondition", str(caught.exception))

    def test_a_skill_without_preconditions_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _deterministic_skill(preconditions=())

    def test_an_unbounded_skill_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as caught:
            _deterministic_skill(max_duration_s=0.0)

        self.assertIn("max_duration_s", str(caught.exception))

    def test_an_unreviewed_skill_is_rejected(self) -> None:
        with self.assertRaises(ValueError) as caught:
            _deterministic_skill(reviewed_by="")

        self.assertIn("review", str(caught.exception))

    def test_a_vla_skill_must_name_its_policy(self) -> None:
        with self.assertRaises(ValueError) as caught:
            _deterministic_skill(kind=SKILL_KIND_VLA, policy=None)

        self.assertIn("policy", str(caught.exception))

    def test_a_deterministic_skill_must_not_carry_a_policy(self) -> None:
        with self.assertRaises(ValueError):
            _deterministic_skill(policy=UNIFOLM_VLA_BASE_G1_EE6D)

    def test_an_unknown_skill_kind_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            _deterministic_skill(kind="natural_language")


class ParameterBindingTest(unittest.TestCase):
    def test_binding_accepts_only_declared_parameters(self) -> None:
        skill = _deterministic_skill()

        with self.assertRaises(ValueError) as caught:
            skill.bind({"target_id": "bench_button_a", "force_n": 4})

        self.assertIn("force_n", str(caught.exception))

    def test_binding_requires_every_declared_parameter(self) -> None:
        skill = _deterministic_skill()

        with self.assertRaises(ValueError) as caught:
            skill.bind({"target_id": "bench_button_a"})

        self.assertIn("approach_speed_mps", str(caught.exception))

    def test_binding_rejects_a_value_outside_the_allowed_set(self) -> None:
        skill = _deterministic_skill()

        with self.assertRaises(ValueError):
            skill.bind(
                {"target_id": "operator_console", "approach_speed_mps": 0.02}
            )

    def test_binding_rejects_a_value_outside_the_numeric_bounds(self) -> None:
        skill = _deterministic_skill()

        with self.assertRaises(ValueError) as caught:
            skill.bind(
                {"target_id": "bench_button_a", "approach_speed_mps": 0.5}
            )

        self.assertIn("approach_speed_mps", str(caught.exception))

    def test_binding_rejects_a_non_numeric_value_for_a_bounded_parameter(
        self,
    ) -> None:
        skill = _deterministic_skill()

        with self.assertRaises(ValueError):
            skill.bind(
                {"target_id": "bench_button_a", "approach_speed_mps": "slow"}
            )

    def test_a_bound_selection_is_reproducible_and_immutable(self) -> None:
        skill = _deterministic_skill()
        arguments = {"target_id": "bench_button_a", "approach_speed_mps": 0.02}

        first = skill.bind(dict(arguments))
        second = skill.bind(dict(arguments))

        self.assertIsInstance(first, SkillSelection)
        self.assertEqual(first.selection_digest(), second.selection_digest())
        self.assertEqual(first.skill_version_id, skill.version_id)
        with self.assertRaises(TypeError):
            first.arguments["target_id"] = "bench_button_b"  # type: ignore[index]

    def test_a_parameter_spec_needs_a_constraint(self) -> None:
        with self.assertRaises(ValueError):
            ParameterSpec(name="freeform")


class SkillRegistryTest(unittest.TestCase):
    def test_only_registered_skills_can_be_selected(self) -> None:
        registry = SkillRegistry()
        registry.register(_deterministic_skill())

        with self.assertRaises(KeyError):
            registry.select(
                "open_drawer",
                {"target_id": "bench_button_a", "approach_speed_mps": 0.02},
            )

    def test_registration_is_append_only_per_revision(self) -> None:
        registry = SkillRegistry()
        registry.register(_deterministic_skill())

        with self.assertRaises(ValueError) as caught:
            registry.register(_deterministic_skill(max_duration_s=99.0))

        self.assertIn("revision", str(caught.exception))

    def test_a_new_revision_does_not_replace_the_previous_one(self) -> None:
        registry = SkillRegistry()
        registry.register(_deterministic_skill())
        registry.register(_deterministic_skill(revision=2, max_duration_s=20.0))

        self.assertEqual(
            registry.get("press_physical_button", revision=1).max_duration_s,
            12.0,
        )
        self.assertEqual(
            registry.get("press_physical_button").revision, 2
        )

    def test_selection_binds_against_the_requested_revision(self) -> None:
        registry = SkillRegistry()
        registry.register(_deterministic_skill())
        registry.register(_deterministic_skill(revision=2))

        selection = registry.select(
            "press_physical_button",
            {"target_id": "bench_button_a", "approach_speed_mps": 0.02},
            revision=1,
        )

        self.assertEqual(selection.skill_version_id, "press_physical_button@1")

    def test_catalog_lists_the_selectable_latest_revisions(self) -> None:
        registry = SkillRegistry()
        registry.register(_deterministic_skill())
        registry.register(_deterministic_skill(revision=2))
        registry.register(
            _deterministic_skill(
                skill_id="place_block",
                kind=SKILL_KIND_VLA,
                policy=UNIFOLM_VLA_BASE_G1_EE6D,
            )
        )

        self.assertEqual(
            registry.catalog(), ("place_block@1", "press_physical_button@2")
        )


if __name__ == "__main__":
    unittest.main()
