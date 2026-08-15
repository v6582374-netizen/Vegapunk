"""Systematic check that instructional prompts live in the Prompt Library.

Module-level prompt-like string constants under ``vegapunk/`` and selected
``third_party/paper_orchestra`` prompt modules must either resolve through the
catalog or appear in ``config/prompts/exemptions.yaml`` with a reason.
"""

from __future__ import annotations

import ast
import fnmatch
import tempfile
import unittest
from pathlib import Path

import yaml

from vegapunk.prompt_library import DEFAULT_LIBRARY_ROOT, prompts

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


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
                found.append((target.id, node.lineno))
    return found


def _runtime_prompt_ids(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()
    library_names = {"prompts", "prompt_library", "_prompt_library", "_library"}
    accessor_functions: set[str] = set()

    def library_call(node: ast.AST) -> ast.Call | None:
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            return None
        receiver = node.func.value
        receiver_name = (
            receiver.id
            if isinstance(receiver, ast.Name)
            else receiver.attr
            if isinstance(receiver, ast.Attribute)
            else None
        )
        if receiver_name in library_names and node.func.attr in {"get", "render"}:
            return node
        return None

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        argument_names = {argument.arg for argument in node.args.args}
        if any(
            call.args
            and isinstance(call.args[0], ast.Name)
            and call.args[0].id in argument_names
            for child in ast.walk(node)
            if (call := library_call(child)) is not None
        ):
            accessor_functions.add(node.name)

    prompt_ids: set[str] = set()
    mapping_names: set[str] = set()
    for node in ast.walk(tree):
        call = library_call(node)
        if call is None and (
            not isinstance(node, ast.Call)
            or not isinstance(node.func, ast.Name)
            or node.func.id not in accessor_functions
        ):
            continue
        if not node.args:
            continue
        argument = node.args[0]
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            prompt_ids.add(argument.value)
        elif isinstance(argument, ast.Subscript) and isinstance(argument.value, ast.Name):
            mapping_names.add(argument.value.id)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id in mapping_names
            for target in node.targets
        ):
            continue
        prompt_ids.update(
            value.value
            for value in node.value.values
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        )
    return prompt_ids


class PromptExternalizationCoverageTest(unittest.TestCase):
    def test_catalog_entries_are_readable(self) -> None:
        for entry in prompts.list():
            text = prompts.get(entry.id)
            self.assertTrue(text.strip(), msg=entry.id)

    def test_no_unexempted_module_level_prompts_remain(self) -> None:
        exemptions = yaml.safe_load((DEFAULT_LIBRARY_ROOT / "exemptions.yaml").read_text())
        patterns = [item["pattern"] for item in exemptions["exemptions"]]

        scan_roots = [
            REPOSITORY_ROOT / "vegapunk",
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

    def test_runtime_prompt_ids_are_registered(self) -> None:
        runtime_ids: set[str] = set()
        scan_roots = [
            REPOSITORY_ROOT / "vegapunk",
            REPOSITORY_ROOT / "third_party" / "paper_orchestra" / "autoraters",
            REPOSITORY_ROOT / "third_party" / "paper_orchestra" / "utils" / "prompt_utils.py",
        ]
        for root in scan_roots:
            paths = [root] if root.is_file() else root.rglob("*.py")
            for path in paths:
                if "__pycache__" not in path.parts:
                    runtime_ids.update(_runtime_prompt_ids(path))

        catalog_ids = {entry.id for entry in prompts.list()}
        self.assertEqual(
            sorted(runtime_ids - catalog_ids),
            [],
            msg="Unregistered runtime Prompt IDs",
        )

    def test_runtime_prompt_id_detection_follows_library_mappings(self) -> None:
        source = '''
from vegapunk.prompt_library import prompts as _library

_PROMPT_IDS = {"first": "test.direct_mapping"}
unrelated = {"mode": "not-a-prompt-id"}

def _load(prompt_id):
    return _library.get(prompt_id)

def direct(name):
    return _library.get(_PROMPT_IDS[name])

def wrapped(name):
    mapping = {"second": "test.wrapped_mapping"}
    return _load(mapping[name])
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prompts.py"
            path.write_text(source, encoding="utf-8")
            self.assertEqual(
                _runtime_prompt_ids(path),
                {"test.direct_mapping", "test.wrapped_mapping"},
            )

    def test_deep_research_facade_loads_from_library(self) -> None:
        from vegapunk.mas.agents.dr_agents.prompts import default_prompts

        text = default_prompts.GLOBAL_PLANNER_PROMPT
        self.assertEqual(text, prompts.get("deep_research.global_planner"))


if __name__ == "__main__":
    unittest.main()
