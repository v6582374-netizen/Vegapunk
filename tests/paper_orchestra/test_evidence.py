from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from internagent.paper_orchestra.evidence import prepare_launch_evidence


class LaunchEvidenceTest(unittest.TestCase):
    def test_collects_citations_and_existing_figures_across_the_launch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            launch_dir = root / "launch"
            for index, (doi, title) in enumerate(
                (("10.1000/one", "Paper One"), ("10.1000/two", "Paper Two")),
                start=1,
            ):
                session = launch_dir / f"session_{index}"
                report = session / "candidate" / "run_0" / "report"
                images = report / "images"
                images.mkdir(parents=True)
                image_name = f"result_{index}.png"
                (images / image_name).write_bytes(f"image-{index}".encode())
                (report / "report.md").write_text(
                    f"![Result {index}](images/{image_name})\n", encoding="utf-8"
                )
                idea = {
                    "references": [
                        {
                            "title": title,
                            "authors": [f"Author {index}"],
                            "year": 2025,
                            "doi": doi,
                        }
                    ],
                    "evidence": [
                        {
                            "title": title,
                            "doi": f"https://doi.org/{doi.upper()}",
                            "content": f"Evidence {index}",
                        }
                    ],
                }
                (session / "traj.json").write_text(
                    json.dumps({"ideas": [idea]}), encoding="utf-8"
                )

            output_dir = root / "paper_orchestra_run" / "evidence"
            evidence = prepare_launch_evidence(
                launch_dir=launch_dir, output_dir=output_dir
            )

            citation_map = json.loads(evidence.citation_map.read_text(encoding="utf-8"))
            figures = json.loads(evidence.figures_info.read_text(encoding="utf-8"))
            self.assertEqual(len(citation_map), 2)
            self.assertIn("Paper One", evidence.references.read_text(encoding="utf-8"))
            self.assertIn("Paper Two", evidence.references.read_text(encoding="utf-8"))
            self.assertEqual(
                {item["caption"] for item in figures}, {"Result 1", "Result 2"}
            )
            self.assertTrue(
                all((output_dir / "figures" / item["name"]).is_file() for item in figures)
            )


if __name__ == "__main__":
    unittest.main()
