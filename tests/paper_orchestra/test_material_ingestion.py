from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from internagent.paper_orchestra.material_ingestion import ingest_research_draft
from tests.paper_orchestra.test_agents import RecordingModel


class MaterialIngestionTest(unittest.TestCase):
    def test_reads_draft_in_block_aligned_batches_and_persists_working_material(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            launch_dir = root / "launch"
            draft_path = launch_dir / "manuscript" / "draft.md"
            draft_path.parent.mkdir(parents=True)
            draft_path.write_text(
                "first measured result\n"
                "<!-- draft-block -->\n"
                r"derived formula: \(L=\sum_i w_i\ell_i\)" + "\n"
                "<!-- draft-block -->\n"
                "citation evidence for Paper A\n",
                encoding="utf-8",
            )
            model = RecordingModel(
                text_responses=[
                    "result",
                    r"formula \(L\)",
                    "citation",
                    "merged paper material with result, formula, and citation",
                ]
            )
            output_dir = root / "paper_orchestra_run" / "working_materials"

            material_path = asyncio.run(
                ingest_research_draft(
                    draft_path=draft_path,
                    launch_dir=launch_dir,
                    output_dir=output_dir,
                    model=model,
                    max_batch_chars=42,
                )
            )

            self.assertEqual(len(model.text_calls), 4)
            for call in model.text_calls[:3]:
                prompt = str(call["prompt"])
                self.assertNotIn("<!-- draft-block -->\n<!-- draft-block -->", prompt)
            self.assertEqual(
                material_path.read_text(encoding="utf-8"),
                "merged paper material with result, formula, and citation\n",
            )
            self.assertEqual(
                sorted(path.name for path in (output_dir / "batches").glob("*.md")),
                ["batch_0001.md", "batch_0002.md", "batch_0003.md"],
            )


if __name__ == "__main__":
    unittest.main()
