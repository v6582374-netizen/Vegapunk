from __future__ import annotations

import unittest
from unittest.mock import patch

from vegapunk.runtime_dependencies import (
    IDEAGRAPH_RUNTIME_REQUIREMENTS,
    RUNTIME_CONSTRAINTS_PATH,
    enforce_runtime_pip_constraint,
    verify_ideagraph_runtime,
)


class RuntimeDependencyContractTest(unittest.TestCase):
    def test_ideagraph_dependency_chain_is_fully_constrained(self) -> None:
        """A task installer cannot replace any package IdeaGraph imports."""
        constraints = {
            line.strip()
            for line in RUNTIME_CONSTRAINTS_PATH.read_text(
                encoding="utf-8"
            ).splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }

        self.assertTrue(
            set(IDEAGRAPH_RUNTIME_REQUIREMENTS).issubset(constraints)
        )

    def test_runtime_constraint_is_inherited_by_child_environments(
        self,
    ) -> None:
        environment: dict[str, str] = {}

        path = enforce_runtime_pip_constraint(environment)

        self.assertEqual(path, RUNTIME_CONSTRAINTS_PATH)
        self.assertEqual(
            environment["PIP_CONSTRAINT"],
            str(RUNTIME_CONSTRAINTS_PATH),
        )

    def test_ideagraph_runtime_dependency_chain_imports(self) -> None:
        verify_ideagraph_runtime()

    def test_ideagraph_preflight_rejects_a_drifted_package(self) -> None:
        expected_versions = {
            requirement.split("==", 1)[0]: requirement.split("==", 1)[1]
            for requirement in IDEAGRAPH_RUNTIME_REQUIREMENTS
        }
        expected_versions["datasets"] = "3.3.2"

        with patch(
            "vegapunk.runtime_dependencies.version",
            side_effect=expected_versions.__getitem__,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "datasets==3.3.2; expected 2.21.0",
            ):
                verify_ideagraph_runtime()


if __name__ == "__main__":
    unittest.main()
