from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from coworker.secrets import SecretStore
from coworker.server import SessionManager, create_app
from coworker.youtube.client import (
    CaptionResult,
    CaptionUnavailable,
    YouTubeAuthError,
    YouTubeClient,
)
from coworker.youtube.service import YouTubeAutomationService
from coworker.youtube.store import YouTubeStore
from coworker.youtube.translation import YouTubeTranslationService


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
    def __init__(self):
        self.caption_requests: list[str] = []

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
        self.caption_requests.append(video_id)
        return CaptionResult("en", "English", "standard", "fake", "Hello")


def test_youtube_service_manual_scan_advances_cursor_only_after_channel_scan(tmp_path):
    store = YouTubeStore(tmp_path / "youtube.db")
    store.set_state("authorized_at", 1)
    client = _FakeClient()
    service = YouTubeAutomationService(store, client)
    result = __import__("asyncio").run(service.scan(now=200))
    assert result.discovered == 1
    assert client.caption_requests == []
    assert store.get_video("abc")["caption_status"] == "pending"
    assert store.get_state("last_scan_at") == 200
    assert result.artifact is None


def test_youtube_service_refreshes_subscriptions_before_discovery(tmp_path):
    class _CurrentSubscriptionsClient(_FakeClient):
        async def list_subscriptions(self):
            return [{"channel_id": "current", "title": "Current channel"}]

        async def fetch_rss(self, channel_id: str):
            if channel_id == "stale":  # pragma: no cover - assertion is the regression test
                raise AssertionError("an unsubscribed channel must not be scanned")
            return []

    store = YouTubeStore(tmp_path / "youtube.db")
    store.replace_channels([{"channel_id": "stale", "title": "Stale channel"}])
    store.upsert_video(
        {
            "video_id": "stale-pending",
            "channel_id": "stale",
            "channel_title": "Stale channel",
            "title": "Polluted discovery",
        }
    )
    store.upsert_video(
        {
            "video_id": "stale-selected",
            "channel_id": "stale",
            "channel_title": "Stale channel",
            "title": "Chosen history",
        }
    )
    store.set_selected("stale-selected", True)
    store.upsert_video(
        {
            "video_id": "stale-caption",
            "channel_id": "stale",
            "channel_title": "Stale channel",
            "title": "Caption history",
        }
    )
    store.set_caption(
        "stale-caption",
        language_code="en",
        language_name="English",
        track_kind="standard",
        source="test",
        body="Keep me",
    )
    store.set_state("authorized_at", 1)

    __import__("asyncio").run(
        YouTubeAutomationService(store, _CurrentSubscriptionsClient()).scan(now=200)
    )

    assert [channel["channel_id"] for channel in store.list_channels()] == ["current"]
    assert store.get_video("stale-pending") is None
    assert store.get_video("stale-selected") is not None
    assert store.get_video("stale-caption") is not None


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
        __import__("asyncio").run(service.scan(now=200))
    assert store.get_state("last_scan_at") == 100


def test_youtube_updates_api_runs_a_manual_scan(tmp_path):
    manager = SessionManager(data_dir=tmp_path / "data")
    manager.youtube_store.set_state("authorized_at", 1)
    youtube_client = _FakeClient()
    manager.youtube = YouTubeAutomationService(manager.youtube_store, youtube_client)

    response = TestClient(create_app(manager)).post("/v1/youtube/updates")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["discovered"] == 1
    assert youtube_client.caption_requests == []
    assert manager.youtube_store.get_video("abc")["caption_status"] == "pending"
    assert manager.youtube_store.get_video("abc")["caption_body"] is None


def test_youtube_caption_api_fetches_only_the_chosen_video(tmp_path):
    manager = SessionManager(data_dir=tmp_path / "data")
    youtube_client = _FakeClient()
    manager.youtube = YouTubeAutomationService(manager.youtube_store, youtube_client)
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

    response = TestClient(create_app(manager)).post("/v1/youtube/videos/abc/caption")

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert youtube_client.caption_requests == ["abc"]
    assert response.json()["video"]["caption_status"] == "ready"
    assert manager.youtube_store.get_video("abc")["caption_body"] == "Hello"


def test_youtube_caption_api_records_a_video_level_failure(tmp_path):
    class _MissingCaptionClient(_FakeClient):
        async def fetch_caption(self, video_id: str):
            self.caption_requests.append(video_id)
            raise CaptionUnavailable("No accessible captions were found.")

    manager = SessionManager(data_dir=tmp_path / "data")
    manager.youtube = YouTubeAutomationService(
        manager.youtube_store, _MissingCaptionClient()
    )
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

    response = TestClient(create_app(manager)).post("/v1/youtube/videos/abc/caption")

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert response.json()["video"]["caption_status"] == "error"
    assert manager.youtube_store.get_video("abc")["caption_error"] == (
        "No accessible captions were found."
    )


def test_youtube_caption_api_rejects_an_unknown_video(tmp_path):
    manager = SessionManager(data_dir=tmp_path / "data")

    response = TestClient(create_app(manager)).post("/v1/youtube/videos/missing/caption")

    assert response.status_code == 404


def test_youtube_caption_fetch_is_decoupled_from_oauth_scope(tmp_path):
    client = YouTubeClient(_secret_store(tmp_path))

    async def caption_data_api_must_not_run(video_id: str):  # pragma: no cover
        raise AssertionError("public caption retrieval must not use the OAuth caption API")

    async def public_transcript(video_id: str):
        return CaptionResult("en", "English", "standard", "public", "Hello")

    client._api_caption_tracks = caption_data_api_must_not_run
    client._transcript_api_caption = public_transcript

    caption = __import__("asyncio").run(client.fetch_caption("abc"))

    assert caption.body == "Hello"


def test_youtube_translation_settings_are_local_and_secret_redacted(tmp_path):
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer translation-key"
        requests.append(__import__("json").loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "OK"}}]},
        )

    secrets = SecretStore(tmp_path / "translation-secrets.json")
    translator = YouTubeTranslationService(
        YouTubeStore(tmp_path / "youtube.db"),
        secrets,
        transport=httpx.MockTransport(handler),
    )
    saved = translator.save_settings(
        base_url="https://models.example/v1/",
        model="translator-model",
        api_key="translation-key",
        prompt="Translate this: {caption}",
    )

    assert saved["configured"] is True
    assert saved["has_api_key"] is True
    assert "api_key" not in saved
    assert secrets.get("youtube:translation")["api_key"] == "translation-key"

    tested = __import__("asyncio").run(translator.test_connection())
    assert tested["ok"] is True
    assert requests[0]["model"] == "translator-model"
    assert requests[0]["messages"][0]["content"] == "Reply with exactly OK."


def test_youtube_translation_uses_editable_prompt_and_persists_chinese(tmp_path):
    prompts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        prompts.append(payload["messages"][0]["content"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": f"中文片段 {len(prompts)}"}}
                ]
            },
        )

    store = YouTubeStore(tmp_path / "youtube.db")
    store.upsert_video(
        {
            "video_id": "abc",
            "channel_id": "chan",
            "channel_title": "Channel",
            "title": "Fresh video",
        }
    )
    store.set_caption(
        "abc",
        language_code="en",
        language_name="English",
        track_kind="standard",
        source="test",
        body="First paragraph.\n\nSecond paragraph.",
    )
    translator = YouTubeTranslationService(
        store,
        SecretStore(tmp_path / "translation-secrets.json"),
        transport=httpx.MockTransport(handler),
        chunk_chars=18,
    )
    translator.save_settings(
        base_url="https://models.example/v1",
        model="translator-model",
        api_key="translation-key",
        prompt="Translate {title} from {language}, part {part}/{parts}:\n{caption}",
    )

    result = __import__("asyncio").run(translator.translate("abc"))

    assert result["ok"] is True
    assert len(prompts) == 2
    assert "Fresh video" in prompts[0]
    assert "part 1/2" in prompts[0]
    video = store.get_video("abc")
    assert video["translation_status"] == "ready"
    assert video["translation_body"] == "中文片段 1\n\n中文片段 2"
    assert video["caption_body"] == "First paragraph.\n\nSecond paragraph."


def test_youtube_translation_api_saves_tests_and_translates(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        content = payload["messages"][0]["content"]
        answer = "OK" if content == "Reply with exactly OK." else "中文译文"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": answer}}]},
        )

    manager = SessionManager(data_dir=tmp_path / "data")
    manager.youtube_translation = YouTubeTranslationService(
        manager.youtube_store,
        SecretStore(tmp_path / "translation-secrets.json"),
        transport=httpx.MockTransport(handler),
    )
    manager.youtube_store.upsert_video(
        {
            "video_id": "abc",
            "channel_id": "chan",
            "channel_title": "Channel",
            "title": "Fresh video",
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

    saved = client.put(
        "/v1/youtube/translation/settings",
        json={
            "base_url": "https://models.example/v1",
            "model": "translator-model",
            "api_key": "translation-key",
            "prompt": "Translate to Chinese:\n{caption}",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["has_api_key"] is True
    assert "api_key" not in saved.json()
    assert client.post("/v1/youtube/translation/test").json()["ok"] is True

    translated = client.post("/v1/youtube/videos/abc/translate")
    assert translated.status_code == 200
    assert translated.json()["ok"] is True
    assert translated.json()["video"]["translation_status"] == "ready"
    assert translated.json()["video"]["translation_body"] == "中文译文"


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


def test_youtube_automation_creation_is_retired(tmp_path):
    manager = SessionManager(data_dir=tmp_path / "data")
    created = manager.create_youtube_automation({})
    assert created["ok"] is False
    assert "manually" in created["error"]


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


def test_youtube_oauth_uses_the_current_browser_redirect_for_start_and_callback(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "client-id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "client-secret")
    manager = SessionManager(data_dir=tmp_path / "data")
    exchanged_redirects: list[str] = []

    async def exchange_code(*, code: str, redirect_uri: str):
        assert code == "authorization-code"
        exchanged_redirects.append(redirect_uri)
        return {"access_token": "access"}

    async def sync_subscriptions():
        return {"ok": True}

    manager.youtube_client.exchange_code = exchange_code
    manager.youtube.sync_subscriptions = sync_subscriptions
    client = TestClient(create_app(manager))
    current_redirect = "https://loongge.tail698656.ts.net/v1/youtube/oauth/callback"

    authorization = client.get(
        "/v1/youtube/oauth/start", params={"redirect_uri": current_redirect}
    ).json()
    query = parse_qs(urlsplit(authorization["authorization_url"]).query)
    assert query["redirect_uri"] == [current_redirect]

    callback = client.get(
        "/v1/youtube/oauth/callback",
        params={"code": "authorization-code", "state": query["state"][0]},
    )
    assert callback.status_code == 200
    assert exchanged_redirects == [current_redirect]


def test_youtube_oauth_settings_persist_and_apply_without_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("YOUTUBE_CLIENT_ID", raising=False)
    monkeypatch.delenv("YOUTUBE_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("YOUTUBE_REDIRECT_URI", raising=False)
    manager = SessionManager(data_dir=tmp_path / "data")
    client = TestClient(create_app(manager))

    initial = client.get("/v1/youtube/oauth/settings").json()
    assert initial["configured"] is False
    assert initial["has_client_secret"] is False
    assert "client_secret" not in initial

    saved = client.put(
        "/v1/youtube/oauth/settings",
        json={
            "client_id": "local-client.apps.googleusercontent.com",
            "client_secret": "local-secret",
            "redirect_uri": "http://localhost:1420/v1/youtube/oauth/callback",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["configured"] is True
    assert saved.json()["source"] == "local"
    assert "client_secret" not in saved.json()
    assert client.get("/v1/youtube/status").json()["configured"] is True

    preserved = client.put(
        "/v1/youtube/oauth/settings",
        json={
            "client_id": "local-client.apps.googleusercontent.com",
            "client_secret": "",
            "redirect_uri": "http://localhost:1420/v1/youtube/oauth/callback",
        },
    )
    assert preserved.json()["ok"] is True

    authorization = client.get("/v1/youtube/oauth/start").json()
    assert authorization["ok"] is True
    query = parse_qs(urlsplit(authorization["authorization_url"]).query)
    assert query["client_id"] == ["local-client.apps.googleusercontent.com"]
    assert query["redirect_uri"] == ["http://localhost:1420/v1/youtube/oauth/callback"]
    assert (
        manager.secrets.get("youtube:oauth_client")["client_secret"] == "local-secret"
    )
