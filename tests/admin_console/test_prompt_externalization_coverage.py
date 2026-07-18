"""Systematic check that instructional prompts live in the Prompt Library.

Module-level prompt-like string constants under ``internagent/`` and selected
``third_party/paper_orchestra`` prompt modules must either resolve through the
catalog or appear in ``config/prompts/exemptions.yaml`` with a reason.
"""

from __future__ import annotations

import ast
import fnmatch
import unittest
from pathlib import Path

import yaml

from internagent.prompt_library import DEFAULT_LIBRARY_ROOT, prompts

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _looks_like_prompt(text: str) -> bool:
    if len(text) < 150:
        return False
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in (
            "you are",
            "your task",
            "guidelines",
            "please carefully",
            "return only",
            "system prompt",
        )
    )


def _matches_exemption(rel: str, pattern: str) -> bool:
    if "**" in pattern:
        prefix = pattern.split("**", 1)[0].rstrip("/")
        return rel == prefix or rel.startswith(prefix + "/")
    return fnmatch.fnmatch(rel, pattern) or pattern in rel


def _module_level_prompts(path: Path) -> list[tuple[str, int]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    found: list[tuple[str, int]] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
            continue
        if not _looks_like_prompt(node.value.value):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                found.append((target.name, node.lineno))
    return found


class PromptExternalizationCoverageTest(unittest.TestCase):
    def test_catalog_entries_are_readable(self) -> None:
        for entry in prompts.list():
            text = prompts.get(entry.id)
            self.assertTrue(text.strip(), msg=entry.id)

    def test_no_unexempted_module_level_prompts_remain(self) -> None:
        exemptions = yaml.safe_load((DEFAULT_LIBRARY_ROOT / "exemptions.yaml").read_text())
        patterns = [item["pattern"] for item in exemptions["exemptions"]]

        scan_roots = [
            REPOSITORY_ROOT / "internagent",
            REPOSITORY_ROOT / "third_party" / "paper_orchestra" / "autoraters",
            REPOSITORY_ROOT / "third_party" / "paper_orchestra" / "utils" / "prompt_utils.py",
        ]
        leftovers: list[str] = []
        for root in scan_roots:
            paths = [root] if root.is_file() else list(root.rglob("*.py"))
            for path in paths:
                if "__pycache__" in path.parts:
                    continue
                rel = str(path.relative_to(REPOSITORY_ROOT))
                if any(_matches_exemption(rel, pattern) for pattern in patterns):
                    continue
                # Facades that only call the library are fine even if they still
                # assign strings via get(); we only flag raw string constants.
                for name, lineno in _module_level_prompts(path):
                    leftovers.append(f"{rel}:{lineno}:{name}")

        self.assertEqual(
            leftovers,
            [],
            msg="Unexternalized module-level prompts:\n" + "\n".join(leftovers),
        )

    def test_deep_research_facade_loads_from_library(self) -> None:
        from internagent.mas.agents.dr_agents.prompts import default_prompts

        text = default_prompts.GLOBAL_PLANNER_PROMPT
        self.assertEqual(text, prompts.get("deep_research.global_planner"))


if __name__ == "__main__":
    unittest.main()
