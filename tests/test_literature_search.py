from __future__ import annotations

import asyncio
import os
import unittest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, call, patch

from vegapunk.mas.tools import literature_search as literature_search_module
from vegapunk.mas.tools.literature_search import LiteratureSearch


class _FakeResponse:
    def __init__(
        self,
        status: int,
        *,
        payload=None,
        headers=None,
        text="",
    ) -> None:
        self.status = status
        self._payload = payload
        self.headers = headers or {}
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def json(self):
        return self._payload

    async def read(self):
        return b""

    async def text(self):
        return self._text


class _FakeSession:
    def __init__(self, responses, calls) -> None:
        self._responses = list(responses)
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    def get(self, url, *, params, headers):
        self.calls.append({"url": url, "params": params, "headers": headers})
        return self._responses.pop(0)


class _NoopLimiter:
    @asynccontextmanager
    async def permit(self):
        yield


class _CountingLimiter(_NoopLimiter):
    def __init__(self) -> None:
        self.entries = 0

    @asynccontextmanager
    async def permit(self):
        self.entries += 1
        yield


class LiteratureSearchTest(unittest.IsolatedAsyncioTestCase):
    async def test_arxiv_rate_limiter_spaces_request_starts(self) -> None:
        limiter = literature_search_module._CrossRefRateLimiter(
            requests_per_window=1,
            window_seconds=0.02,
            max_concurrent=1,
        )
        loop = asyncio.get_running_loop()
        started_at = []

        async def acquire() -> None:
            async with limiter.permit():
                started_at.append(loop.time())

        await asyncio.gather(acquire(), acquire())

        self.assertEqual(len(started_at), 2)
        self.assertGreaterEqual(started_at[1] - started_at[0], 0.015)

    async def test_arxiv_search_uses_the_polite_request_limiter(self) -> None:
        calls = []
        limiter = _CountingLimiter()

        def fake_session(**_kwargs):
            return _FakeSession([_FakeResponse(200)], calls)

        with patch.object(
            literature_search_module.aiohttp,
            "ClientSession",
            side_effect=fake_session,
        ), patch.object(
            literature_search_module,
            "_ARXIV_LIMITER",
            limiter,
        ):
            papers = await LiteratureSearch({}).search_arxiv("agent systems")

        self.assertEqual(papers, [])
        self.assertEqual(limiter.entries, 1)
        self.assertEqual(len(calls), 1)

    async def test_crossref_uses_launch_injected_email_and_retries_429(self) -> None:
        payload = {
            "message": {
                "items": [
                    {
                        "title": ["A paper"],
                        "author": [{"given": "Ada", "family": "Lovelace"}],
                        "published": {"date-parts": [[2026]]},
                        "container-title": ["Journal"],
                        "DOI": "10.1234/example",
                        "URL": "https://doi.org/10.1234/example",
                    }
                ]
            }
        }
        calls = []
        responses = [
            _FakeResponse(429, headers={"Retry-After": "2"}),
            _FakeResponse(200, payload=payload),
        ]

        def fake_session(**_kwargs):
            return _FakeSession(responses, calls)

        with patch.dict(os.environ, {"CROSSREF_EMAIL": "real@example.com"}), patch.object(
            literature_search_module.aiohttp, "ClientSession", side_effect=fake_session
        ), patch.object(
            literature_search_module, "_CROSSREF_LIMITER", _NoopLimiter()
        ), patch.object(
            literature_search_module.asyncio, "sleep", new=AsyncMock()
        ) as sleep:
            search = LiteratureSearch({})
            papers = await search.search_crossref("generative AI", max_results=1)

        self.assertEqual(search.email, "real@example.com")
        self.assertEqual(len(papers), 1)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["params"]["mailto"], "real@example.com")
        self.assertIn("mailto:real@example.com", calls[0]["headers"]["User-Agent"])
        self.assertEqual(sleep.await_args_list, [call(2.0)])

    def test_explicit_config_email_overrides_injected_environment(self) -> None:
        with patch.dict(os.environ, {"CROSSREF_EMAIL": "environment@example.com"}):
            search = LiteratureSearch({"email": "config@example.com"})

        self.assertEqual(search.email, "config@example.com")

    def test_missing_email_does_not_fabricate_a_contact_identity(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            search = LiteratureSearch({})

        self.assertEqual(search.email, "")
        self.assertNotIn("mailto", search.headers["User-Agent"])


if __name__ == "__main__":
    unittest.main()
