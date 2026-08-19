from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from coworker.secrets import SecretStore
from coworker.server import SessionManager, create_app
from coworker.youtube.client import CaptionResult, YouTubeAuthError, YouTubeClient
from coworker.youtube.service import YouTubeAutomationService
from coworker.youtube.store import YouTubeStore


def _secret_store(tmp_path: Path) -> SecretStore:
    store = SecretStore(tmp_path / "secrets.json")
    store.put(
        "youtube:default",
        {
            "type": "oauth",
            "access_token": "access",
            "refresh_token": "refresh",
            "expires": time.time() + 3600,
        },
    )
    return store


def test_youtube_store_is_idempotent_and_delete_is_tombstoned(tmp_path):
    store = YouTubeStore(tmp_path / "youtube.db")
    video = {
        "video_id": "abc",
        "channel_id": "chan",
        "channel_title": "Channel",
        "title": "A video",
        "url": "https://www.youtube.com/watch?v=abc",
        "published_at": "2026-08-19T00:00:00Z",
        "published_ts": 1787097600,
    }
    assert store.upsert_video(video) is True
    assert store.upsert_video(video) is False
    store.set_caption(
        "abc",
        language_code="en",
        language_name="English",
        track_kind="standard",
        source="test",
        body="Hello",
    )
    assert store.set_selected("abc", True) is True
    assert store.get_video("abc")["caption_body"] == "Hello"
    assert store.delete_video("abc") is True
    assert store.get_video("abc") is None
    assert store.upsert_video(video) is False


def test_youtube_client_lists_paginated_subscriptions(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer access"
        if request.url.path.endswith("/subscriptions") and request.url.params.get("pageToken") is None:
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "snippet": {
                                "resourceId": {"channelId": "chan-1"},
                                "title": "One",
                                "publishedAt": "2026-08-01T00:00:00Z",
                            }
                        }
                    ],
                    "nextPageToken": "next",
                },
            )
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "snippet": {
                            "resourceId": {"channelId": "chan-2"},
                            "title": "Two",
                        }
                    }
                ]
            },
        )

    client = YouTubeClient(
        _secret_store(tmp_path), client_id="client", client_secret="secret", transport=httpx.MockTransport(handler)
    )
    channels = __import__("asyncio").run(client.list_subscriptions())
    assert [channel["channel_id"] for channel in channels] == ["chan-1", "chan-2"]


def test_youtube_client_parses_rss(tmp_path):
    xml = """<?xml version='1.0' encoding='UTF-8'?>
    <feed xmlns='http://www.w3.org/2005/Atom' xmlns:yt='http://www.youtube.com/xml/schemas/2015'>
      <entry>
        <yt:videoId>abc</yt:videoId>
        <yt:channelId>chan</yt:channelId>
        <title>Fresh &amp; Useful</title>
        <published>2026-08-19T00:00:00+00:00</published>
        <updated>2026-08-19T01:00:00+00:00</updated>
        <author><name>Channel</name></author>
      </entry>
    </feed>"""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["channel_id"] == "chan"
        return httpx.Response(200, text=xml)

    client = YouTubeClient(_secret_store(tmp_path), transport=httpx.MockTransport(handler))
    entries = __import__("asyncio").run(client.fetch_rss("chan"))
    assert entries[0]["video_id"] == "abc"
    assert entries[0]["title"] == "Fresh & Useful"


class _FakeClient:
    async def ensure_authorized(self):
        return None

    async def list_subscriptions(self):
        return [{"channel_id": "chan", "title": "Channel"}]

    async def fetch_rss(self, channel_id: str):
        return [
            {
                "video_id": "abc",
                "channel_id": channel_id,
                "channel_title": "Channel",
                "title": "Fresh",
                "url": "https://youtu.be/abc",
                "published_at": "2026-08-19T00:00:00Z",
                "published_ts": 100,
            }
        ]

    async def fetch_caption(self, video_id: str):
        return CaptionResult("en", "English", "standard", "fake", "Hello")


def test_youtube_service_advances_cursor_only_after_channel_scan(tmp_path):
    store = YouTubeStore(tmp_path / "youtube.db")
    store.set_state("authorized_at", 1)
    service = YouTubeAutomationService(store, _FakeClient())
    result = __import__("asyncio").run(
        service.run(task_id="task-youtube", workspace=tmp_path / "workspace", now=200)
    )
    assert result.discovered == 1
    assert result.captions_ready == 1
    assert store.get_state("last_scan_at") == 200
    artifact = tmp_path / "workspace" / result.artifact
    assert json.loads(artifact.read_text())["discovered"] == 1


def test_youtube_service_fails_before_rss_when_authorization_is_invalid(tmp_path):
    class _UnauthorizedClient(_FakeClient):
        async def ensure_authorized(self):
            raise YouTubeAuthError("expired")

        async def fetch_rss(self, channel_id: str):  # pragma: no cover - should never run
            raise AssertionError("RSS must not be queried without authorization")

    store = YouTubeStore(tmp_path / "youtube.db")
    store.set_state("authorized_at", 1)
    store.set_state("last_scan_at", 100)
    service = YouTubeAutomationService(store, _UnauthorizedClient())
    with pytest.raises(YouTubeAuthError):
        __import__("asyncio").run(
            service.run(task_id="task-youtube", workspace=tmp_path / "workspace", now=200)
        )
    assert store.get_state("last_scan_at") == 100


def test_youtube_caption_auth_error_does_not_fallback_to_public_transcript(tmp_path):
    client = YouTubeClient(_secret_store(tmp_path))

    async def auth_error(video_id: str):
        raise YouTubeAuthError("expired")

    async def should_not_run(video_id: str):  # pragma: no cover - assertion is the test
        raise AssertionError("public transcript fallback must not run after auth failure")

    client._api_caption_tracks = auth_error
    client._transcript_api_caption = should_not_run
    with pytest.raises(YouTubeAuthError):
        __import__("asyncio").run(client.fetch_caption("abc"))


def test_youtube_oauth_reauthorization_preserves_existing_refresh_token(tmp_path):
    secrets = _secret_store(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/token")
        return httpx.Response(200, json={"access_token": "new-access", "expires_in": 3600})

    client = YouTubeClient(
        secrets,
        client_id="client",
        client_secret="secret",
        transport=httpx.MockTransport(handler),
    )

    async def no_identity():
        return None

    client.current_channel = no_identity
    profile = __import__("asyncio").run(client.exchange_code(code="code", redirect_uri="http://localhost/callback"))
    assert profile["access_token"] == "new-access"
    assert profile["refresh_token"] == "refresh"


def test_youtube_automation_has_beijing_midnight_schedule(tmp_path):
    manager = SessionManager(data_dir=tmp_path / "data")
    created = manager.create_youtube_automation({})
    assert created["ok"] is True
    task = manager.task_store.get(created["task"]["id"])
    assert task is not None
    assert task.kind == "youtube"
    assert task.schedule.cron == "0 0 * * *"
    assert task.schedule.timezone == "Asia/Shanghai"


def test_youtube_video_api_exposes_selection_and_delete(tmp_path):
    manager = SessionManager(data_dir=tmp_path / "data")
    manager.youtube_store.upsert_video(
        {
            "video_id": "abc",
            "channel_id": "chan",
            "channel_title": "Channel",
            "title": "Fresh",
            "url": "https://youtu.be/abc",
            "published_at": "2026-08-19T00:00:00Z",
            "published_ts": 100,
        }
    )
    manager.youtube_store.set_caption(
        "abc",
        language_code="en",
        language_name="English",
        track_kind="standard",
        source="test",
        body="Hello",
    )
    client = TestClient(create_app(manager))
    listed = client.get("/v1/youtube/videos")
    assert listed.status_code == 200
    assert listed.json()["videos"][0]["caption"]["language_code"] == "en"
    assert client.patch("/v1/youtube/videos/abc", json={"selected": True}).json()["ok"] is True
    detail = client.get("/v1/youtube/videos/abc").json()["video"]
    assert detail["selected"] is True
    assert detail["caption_body"] == "Hello"
    assert client.delete("/v1/youtube/videos/abc").json()["ok"] is True


def test_youtube_oauth_start_is_server_side_and_requires_client_config(tmp_path, monkeypatch):
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "client-id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "client-secret")
    manager = SessionManager(data_dir=tmp_path / "data")
    client = TestClient(create_app(manager))
    response = client.get("/v1/youtube/oauth/start")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert "accounts.google.com" in payload["authorization_url"]
    assert "youtube.readonly" in payload["authorization_url"]
