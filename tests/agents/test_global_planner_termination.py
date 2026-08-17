from __future__ import annotations

import logging
import sys
import unittest
from types import SimpleNamespace

_PRE_IMPORT_MODULES = set(sys.modules)
_PRE_IMPORT_PATH = list(sys.path)

from vegapunk.mas.agents.dr_agents.agents.global_planner_agent import (  # noqa: E402
    GlobalPlannerAgent,
    PlanGenerationError,
)

# The DeepResearch tree appends its own directories to sys.path at import time.
# Its ``utils`` is a regular package, and a regular package anywhere on the path
# always outranks a namespace package -- so once those entries are present, the
# top-level name ``utils`` resolves to DeepResearch's for the rest of the
# session, and the vendored paper_orchestra ``utils`` becomes unimportable.
# Returning both borrowed resources keeps this test's result, and everyone
# else's, independent of collection order.
sys.path[:] = _PRE_IMPORT_PATH
for _name in sorted(set(sys.modules) - _PRE_IMPORT_MODULES):
    if _name == "utils" or _name.startswith("utils."):
        del sys.modules[_name]


def _planner(*, step, build=None, max_rebuilds=3):
    """Build a planner with its collaborators replaced, bypassing __init__.

    ``execute`` is the unit under test; model access, tool discovery and prompt
    loading are not, and constructing them would require a live Runtime.
    """

    planner = object.__new__(GlobalPlannerAgent)
    planner.logger = logging.getLogger("test.global_planner")
    planner.max_iter = 5
    planner.max_retries = 2
    planner.max_rebuilds = max_rebuilds
    planner.graph = None
    planner.tool_manager = SimpleNamespace(
        list_tools=lambda: [],
        get_simple_tool_info=lambda tool: tool,
    )
    planner.calls = []

    def execute_one_step(*args, **kwargs):
        planner.calls.append(kwargs.get("current_iter"))
        return step(len(planner.calls))

    planner.execute_one_step = execute_one_step
    if build is not None:
        planner.build_graph_from_plan = build
    return planner


class GlobalPlannerTerminationTest(unittest.TestCase):
    def test_an_unparseable_model_does_not_loop_forever(self) -> None:
        """A planner that can never parse a reply must fail, not spin."""

        planner = _planner(step=lambda _: None)

        with self.assertRaises(PlanGenerationError):
            planner.execute("Investigate solid-state electrolytes.")

        # Bounded by max_retries alone: no outer loop may reopen the attempt.
        self.assertEqual(len(planner.calls), planner.max_retries)

    def test_a_persistently_cyclic_plan_is_abandoned(self) -> None:
        """Rebuilding on a cycle is allowed, but not without end."""

        graph = {
            "nodes": [{"node_id": "task", "type": "answer", "task": "t"}],
            "edges": [],
        }
        rebuilds = []

        def always_cyclic(plan):
            rebuilds.append(plan)
            return None

        planner = _planner(
            step=lambda _: graph,
            build=always_cyclic,
            max_rebuilds=3,
        )

        with self.assertRaises(PlanGenerationError):
            planner.execute("Investigate solid-state electrolytes.")

        # Bounded, not zero: it kept trying, then gave up instead of spinning.
        self.assertEqual(len(rebuilds), 3)
        self.assertLessEqual(len(planner.calls), 3 * planner.max_iter)

    def test_a_late_failure_keeps_the_plan_already_refined(self) -> None:
        """Losing iteration three must not discard iterations one and two."""

        refined = {
            "nodes": [
                {"node_id": "task", "type": "answer", "task": "t"},
                {"node_id": "n2", "type": "solve", "task": "s"},
            ],
            "edges": [],
        }
        built = []

        def step(call_index):
            return refined if call_index == 1 else None

        planner = _planner(
            step=step,
            build=lambda plan: built.append(plan) or SimpleNamespace(),
        )

        result = planner.execute("Investigate solid-state electrolytes.")

        self.assertEqual(result, refined)
        self.assertEqual(built, [refined])


if __name__ == "__main__":
    unittest.main()
