from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from internagent.paper_orchestra import run_paper_orchestra
from tests.paper_orchestra.test_vendored_service import _write_launch


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VENDOR_ROOT = REPOSITORY_ROOT / "third_party/paper_orchestra"
_TRANSLATION_REQUEST_MARKER = (
    "Translate the following complete final LaTeX paper"
)

PAPER_TEX = r"""\documentclass{article}
\title{Mock PaperOrchestra Paper}
\author{Anonymous}
\begin{document}
\maketitle
\begin{abstract}
This paper reports a deterministic integration experiment.
\end{abstract}
\section{Introduction}
We study a small measured system.
\section{Method}
The method follows the supplied candidate notes.
\section{Experiments}
The recorded loss improves from 1.0 to 0.5.
\section{Conclusion}
The integration path produces a complete paper.
\end{document}
"""

CHINESE_PAPER_TEX = r"""\documentclass{article}
\title{模拟 PaperOrchestra 论文}
\author{Anonymous}
\begin{document}
\maketitle
\begin{abstract}
本文报告一个确定性的集成实验。
\end{abstract}
\section{引言}
我们研究一个小型测量系统。
\section{方法}
该方法遵循所提供的候选方案说明。
\section{实验}
记录的损失从 1.0 改善到 0.5。
\section{结论}
集成路径生成了一篇完整论文。
\end{document}
"""

OUTLINE = {
    "plotting_plan": [],
    "intro_related_work_plan": {
        "introduction_strategy": {
            "hook_hypothesis": "A measured system needs a reproducible paper.",
            "problem_gap_hypothesis": "The paper pipeline was not connected.",
            "search_directions": [],
        },
        "related_work_strategy": {"overview": "", "subsections": []},
    },
    "section_plan": [
        {
            "section_title": "Method",
            "subsections": [
                {
                    "subsection_title": "Method",
                    "content_bullets": ["Use the supplied candidate notes."],
                    "citation_hints": [],
                }
            ],
        },
        {
            "section_title": "Experiments",
            "subsections": [
                {
                    "subsection_title": "Results",
                    "content_bullets": ["Report loss 1.0 and 0.5."],
                    "citation_hints": [],
                }
            ],
        },
    ],
}


@unittest.skipUnless(shutil.which("pdflatex"), "pdflatex is required")
class UpstreamMockEndToEndTest(unittest.TestCase):
    def test_completes_vendored_pipeline_with_mocked_responses(self) -> None:
        relay = _MockResponsesRelay()
        relay.start()
        self.addCleanup(relay.close)

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            launch_dir = root / "launch"
            _write_launch(launch_dir)
            config_path = root / "paper_orchestra.yaml"
            config_path.write_text(
                f"""vendor_root: {VENDOR_ROOT}
template_dir: templates/iclr2025
use_plotting: true
writer_model: mock-model
reflection_model: mock-model
plotting_model: mock-model
image_model: mock-image-model
max_concurrent_model_requests: 2
plotting_max_critic_rounds: 0
research_cutoff: 2025-01
""",
                encoding="utf-8",
            )

            result = asyncio.run(
                run_paper_orchestra(
                    launch_dir=launch_dir,
                    internagent_config={
                        "models": {
                            "openai": {
                                "api_mode": "responses",
                                "api_key": "mock-key",
                                "base_url": relay.base_url,
                                "model_name": "mock-model",
                                "temperature": 0,
                                "timeout": 60,
                                "reasoning": {
                                    "effort": "low",
                                    "context": "current_turn",
                                    "mode": "standard",
                                },
                                "store": False,
                                "prompt_cache": {
                                    "mode": "implicit",
                                    "ttl": "30m",
                                },
                                "response_state": {"mode": "replay"},
                            }
                        }
                    },
                    paper_config_path=config_path,
                )
            )

            if result.error is not None:
                stdout = (result.run_dir / "stdout.log").read_text(
                    encoding="utf-8", errors="replace"
                )
                stderr = (result.run_dir / "stderr.log").read_text(
                    encoding="utf-8", errors="replace"
                )
                self.fail(f"{result.error}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}")
            self.assertTrue(result.final_pdf.is_file())
            self.assertTrue(result.final_tex.is_file())
            self.assertEqual(result.final_pdf.name, "final_paper.pdf")
            self.assertEqual(result.final_tex.name, "final_refined_paper.tex")
            chinese_tex = result.run_dir.joinpath(
                "content_refinement_workdir",
                "final_paper.zh-CN.tex",
            )
            self.assertIn("模拟 PaperOrchestra 论文", chinese_tex.read_text())
            self.assertTrue(
                (result.run_dir / "final_paper.zh-CN.pdf").is_file()
            )
            self.assertTrue((result.run_dir / "outline.json").is_file())
            self.assertTrue(
                (result.run_dir / "literature_agent_output/outline_v1.json").is_file()
            )
            self.assertGreaterEqual(len(relay.requests), 10)
            self.assertTrue(
                any("input_image" in json.dumps(request) for request in relay.requests)
            )
            translation_requests = [
                request
                for request in relay.requests
                if _TRANSLATION_REQUEST_MARKER
                in json.dumps(request, ensure_ascii=False)
            ]
            self.assertEqual(len(translation_requests), 1)
            self.assertNotIn("tools", translation_requests[0])
            self.assertNotIn(
                "namespace",
                json.dumps(translation_requests[0], ensure_ascii=False),
            )


class _MockResponsesRelay:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []
        self.review_requests = 0
        self._lock = threading.Lock()
        relay = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                request = json.loads(self.rfile.read(length))
                with relay._lock:
                    relay.requests.append(request)
                    text = relay._response_text(request)
                    response_number = len(relay.requests)
                body = json.dumps(
                    {
                        "id": f"resp_{response_number}",
                        "object": "response",
                        "created_at": 0,
                        "status": "completed",
                        "model": request.get("model", "mock-model"),
                        "output": [
                            {
                                "id": f"msg_{response_number}",
                                "type": "message",
                                "status": "completed",
                                "role": "assistant",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": text,
                                        "annotations": [],
                                    }
                                ],
                            }
                        ],
                        "usage": {
                            "input_tokens": 1,
                            "output_tokens": 1,
                            "total_tokens": 2,
                            "input_tokens_details": {"cached_tokens": 0},
                            "output_tokens_details": {"reasoning_tokens": 0},
                        },
                    }
                ).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_: object) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/v1"

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _response_text(self, request: dict[str, object]) -> str:
        serialized = json.dumps(request, ensure_ascii=False)
        if _TRANSLATION_REQUEST_MARKER in serialized:
            return f"```latex\n{CHINESE_PAPER_TEX}\n```"
        if "Analyze the provided page images" in serialized:
            return json.dumps({"figure_and_tables": {}, "other_issues": []})
        if "REFLECTION ITERATION" in serialized:
            return (
                '```json\n{"changes": ["retain the valid draft"]}\n```\n'
                f"```latex\n{PAPER_TEX}\n```"
            )
        if "REVIEW JSON:" in serialized or "meta-reviewing a paper" in serialized:
            self.review_requests += 1
            score = 8 if self.review_requests <= 4 else 7
            axis = 4 if score == 8 else 3
            return json.dumps(
                {
                    "Summary": "A complete integration paper.",
                    "Strengths": ["The pipeline completes."],
                    "Weaknesses": [],
                    "Originality": axis,
                    "Quality": axis,
                    "Clarity": axis,
                    "Significance": axis,
                    "Questions": [],
                    "Limitations": [],
                    "Ethical Concerns": False,
                    "Soundness": axis,
                    "Presentation": axis,
                    "Contribution": axis,
                    "Overall": score,
                    "Confidence": 4,
                    "Decision": "Accept",
                }
            )
        if "Return the **full** compilable LaTeX file" in serialized:
            return f"```latex\n{PAPER_TEX}\n```"
        if "Generate the LaTeX for Introduction and Related Work" in serialized:
            return f"```latex\n{PAPER_TEX}\n```"
        if "convert the provided methodology and experimental logs" in serialized:
            return json.dumps(OUTLINE)
        return json.dumps({})


if __name__ == "__main__":
    unittest.main()
