from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from vegapunk.mas.agents import survey_agent as survey_agent_module
from vegapunk.mas.agents.survey_agent import SurveyAgent


class SurveyAgentPdfDownloadTest(unittest.IsolatedAsyncioTestCase):
    async def test_deep_read_prefers_the_explicit_pdf_url(self) -> None:
        """An arXiv abstract page must never be used as the PDF download URL."""
        agent = object.__new__(SurveyAgent)
        agent.max_papers = 1
        agent.max_concurrent_tasks = 1
        agent.max_concurrent_search_tasks = 1
        agent.literature_search_query = AsyncMock(
            return_value={
                "arxiv": [
                    {
                        "title": "A paper",
                        "authors": ["Ada Lovelace"],
                        "abstract": "Abstract",
                        "content": "",
                        "year": 2026,
                        "doi": None,
                        "url": "https://arxiv.org/abs/1234.5678",
                        "pdf_url": "https://arxiv.org/pdf/1234.5678.pdf",
                        "source": "arxiv",
                        "citations": 0,
                    }
                ]
            }
        )
        agent._call_model = AsyncMock(
            side_effect=[
                'Input("text") Output("answer")',
                "KeywordQuery('test query')",
                {"0": 10},
                {
                    "background": "background",
                    "contributions": "contributions",
                    "methods": "methods",
                    "challenges": "challenges",
                },
            ]
        )

        with patch.object(
            survey_agent_module,
            "download_pdf",
            return_value="/tmp/paper.pdf",
        ) as download_pdf, patch.object(
            survey_agent_module,
            "extract_text_from_pdf",
            return_value="paper body",
        ):
            papers, _ = await agent.advanced_query_paper(
                {"description": "test", "domain": "test"}
            )

        self.assertEqual(len(papers), 1)
        download_pdf.assert_called_once_with(
            "https://arxiv.org/pdf/1234.5678.pdf",
            save_folder="tmp/pdf",
        )


if __name__ == "__main__":
    unittest.main()
