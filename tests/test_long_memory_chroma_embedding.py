from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
import warnings

import numpy as np

CHROMA_AVAILABLE = importlib.util.find_spec("chromadb") is not None

if CHROMA_AVAILABLE:
    from vegapunk.mas.memory.long_memory import IdeaGraph
else:  # pragma: no cover - exercised only in dependency-light environments
    IdeaGraph = None  # type: ignore[assignment,misc]


@unittest.skipUnless(
    CHROMA_AVAILABLE,
    "ChromaDB is an optional long-memory dependency",
)
class LongMemoryChromaEmbeddingTest(unittest.TestCase):
    def test_local_embedding_dependency_chain_imports(self) -> None:
        """The configured local embedding backend must load before IdeaGraph starts."""
        result = subprocess.run(
            [sys.executable, "-c", "from sentence_transformers import SentenceTransformer"],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(
            result.returncode,
            0,
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )

    def test_runtime_embedding_function_creates_and_queries_collection(self) -> None:
        class FakeEmbeddingModel:
            model_type = "local"
            model_name = "test-embedding"

            def encode(self, texts: list[str]) -> np.ndarray:
                return np.asarray(
                    [[0.1, 0.2, 0.3] for _ in texts],
                    dtype=np.float32,
                )

        class FakeRuntime:
            def embedding_model(self) -> FakeEmbeddingModel:
                return FakeEmbeddingModel()

        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            with tempfile.TemporaryDirectory() as working_dir:
                graph = IdeaGraph(
                    working_dir=working_dir,
                    namespace="idea_memory",
                    runtime=FakeRuntime(),
                )

                self.assertIsNotNone(graph.collection)

                graph.add_idea_node(
                    {
                        "id": "idea-1",
                        "name": "Test idea",
                        "description": "A deterministic embedding test.",
                    }
                )

                self.assertIn("idea-1", graph.graph)
                self.assertIn("idea-1", graph.retrieve_related_ideas("test idea"))

            legacy_warnings = [
                warning
                for warning in caught_warnings
                if "legacy embedding function config" in str(warning.message)
            ]
            self.assertEqual(legacy_warnings, [])


if __name__ == "__main__":
    unittest.main()
