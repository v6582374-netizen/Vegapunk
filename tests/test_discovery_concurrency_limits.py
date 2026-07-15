from __future__ import annotations

import unittest
import ast
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]


def _module_assignments(path: Path) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assignments: dict[str, object] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                try:
                    assignments[target.id] = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    pass
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
                and target.attr == "max_concurrent_tasks"
            ):
                try:
                    assignments[target.attr] = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    pass
    return assignments


class DiscoveryConcurrencyLimitTest(unittest.TestCase):
    def test_llm_and_search_limits_are_distinct(self) -> None:
        orchestration = _module_assignments(
            REPOSITORY_ROOT / "internagent/mas/workflow/orchestration_agent.py"
        )
        survey = _module_assignments(
            REPOSITORY_ROOT / "internagent/mas/agents/survey_agent.py"
        )

        self.assertEqual(orchestration["MAX_CONCURRENT_LLM_TASKS"], 2)
        self.assertEqual(orchestration["MAX_CONCURRENT_SEARCH_TASKS"], 10)
        self.assertEqual(survey["MAX_CONCURRENT_LLM_TASKS"], 2)
        self.assertEqual(survey["MAX_CONCURRENT_SEARCH_TASKS"], 10)


if __name__ == "__main__":
    unittest.main()
