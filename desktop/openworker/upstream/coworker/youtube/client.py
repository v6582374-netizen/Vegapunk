"""YouTube OAuth, Data API, RSS, and caption fallbacks."""

from __future__ import annotations

import asyncio
import html
import os
import secrets as token_secrets
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

from ..secrets import SecretStore

YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
API_BASE = "https://www.googleapis.com/youtube/v3"
RSS_BASE = "https://www.youtube.com/feeds/videos.xml"


class YouTubeClientError(RuntimeError):
    """A remote YouTube operation failed."""


class YouTubeAuthError(YouTubeClientError):
    """The user must connect or re-authorize YouTube before fetching."""


class CaptionUnavailable(YouTubeClientError):
    """No allowed caption source could provide a transcript."""


class YouTubeApiError(YouTubeClientError):
    def __init__(self, message: str, *, status_code: int = 0, payload: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


@dataclass(frozen=True)
class CaptionResult:
    language_code: str
    language_name: str
    track_kind: str
    source: str
    body: str


def _published_ts(value: str) -> Optional[float]:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _caption_rank(language_code: str, track_kind: str) -> tuple[int, int, str]:
    language = (language_code or "").lower()
    english = language == "en" or language.startswith("en-")
    # English is preferred, and manual tracks are preferred over generated tracks.
    return (0 if english else 1, 0 if track_kind != "ASR" else 1, language)


class YouTubeClient:
    """Small REST client with injectable HTTP transport for end-to-end tests."""

    def __init__(
        self,
        secrets: SecretStore,
        *,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ) -> None:
        self.secrets = secrets
        self.client_id = client_id or os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
        self.client_secret = client_secret or os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
        self.transport = transport
        self._http: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "YouTubeClient":
        await self._client()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                transport=self.transport,
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
            )
        return self._http

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def profile(self) -> dict[str, Any]:
        return dict(self.secrets.get("youtube:default") or {})

    def status(self) -> dict[str, Any]:
        profile = self.profile()
        if not profile:
            return {
                "configured": self.configured(),
                "connected": False,
                "needs_authorization": True,
            }
        return {
            "configured": self.configured(),
            "connected": bool(profile.get("refresh_token") or profile.get("access_token")),
            "needs_authorization": bool(profile.get("needs_authorization")),
            "account_id": profile.get("account_id"),
            "account_title": profile.get("account_title"),
            "connected_at": profile.get("connected_at"),
        }

    def authorization_url(self, *, state: str, redirect_uri: str) -> str:
        if not self.configured():
            raise YouTubeAuthError(
                "Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET before connecting YouTube."
            )
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": YOUTUBE_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{AUTH_ENDPOINT}?{urlencode(params)}"

    async def exchange_code(self, *, code: str, redirect_uri: str) -> dict[str, Any]:
        if not self.configured():
            raise YouTubeAuthError("YouTube OAuth client is not configured.")
        response = await (await self._client()).post(
            TOKEN_ENDPOINT,
            data={
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        payload = self._json_or_empty(response)
        if response.status_code >= 400 or not payload.get("access_token"):
            raise YouTubeAuthError(
                str(payload.get("error_description") or payload.get("error") or "OAuth exchange failed")
            )
        profile = {
            "type": "oauth",
            "access_token": payload["access_token"],
            "refresh_token": payload.get("refresh_token"),
            "expires": time.time() + float(payload.get("expires_in", 3600)),
            "token_type": payload.get("token_type", "Bearer"),
            "needs_authorization": False,
            "connected_at": time.time(),
        }
        self.secrets.put("youtube:default", profile)
        try:
            identity = await self.current_channel()
        except YouTubeClientError:
            identity = None
        if identity:
            profile.update(
                {
                    "account_id": identity.get("channel_id"),
                    "account_title": identity.get("title"),
                }
            )
            self.secrets.put("youtube:default", profile)
        return profile

    async def refresh_access_token(self) -> str:
        profile = self.profile()
        refresh_token = profile.get("refresh_token")
        if not refresh_token or not self.configured():
            raise YouTubeAuthError("YouTube authorization is not available.")
        response = await (await self._client()).post(
            TOKEN_ENDPOINT,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        payload = self._json_or_empty(response)
        if response.status_code >= 400 or not payload.get("access_token"):
            profile["needs_authorization"] = True
            self.secrets.put("youtube:default", profile)
            raise YouTubeAuthError(
                str(payload.get("error_description") or payload.get("error") or "Token refresh failed")
            )
        profile.update(
            {
                "access_token": payload["access_token"],
                "expires": time.time() + float(payload.get("expires_in", 3600)),
                "needs_authorization": False,
            }
        )
        self.secrets.put("youtube:default", profile)
        return str(payload["access_token"])

    async def access_token(self) -> str:
        profile = self.profile()
        if profile.get("needs_authorization"):
            raise YouTubeAuthError("YouTube authorization has expired. Connect YouTube again.")
        token = profile.get("access_token")
        expires = float(profile.get("expires") or 0)
        if token and expires > time.time() + 60:
            return str(token)
        return await self.refresh_access_token()

    async def current_channel(self) -> Optional[dict[str, Any]]:
        payload = await self.api_json(
            "/channels", {"part": "id,snippet", "mine": "true", "maxResults": 1}
        )
        item = (payload.get("items") or [None])[0]
        if not item:
            return None
        snippet = item.get("snippet") or {}
        return {
            "channel_id": item.get("id"),
            "title": snippet.get("title") or item.get("id"),
        }

    async def list_subscriptions(self) -> list[dict[str, Any]]:
        subscriptions: list[dict[str, Any]] = []
        page_token: Optional[str] = None
        while True:
            params: dict[str, Any] = {
                "part": "snippet",
                "mine": "true",
                "maxResults": 50,
            }
            if page_token:
                params["pageToken"] = page_token
            payload = await self.api_json("/subscriptions", params)
            for item in payload.get("items") or []:
                snippet = item.get("snippet") or {}
                resource = snippet.get("resourceId") or {}
                channel_id = resource.get("channelId")
                if not channel_id:
                    continue
                thumbs = snippet.get("thumbnails") or {}
                thumbnail = (thumbs.get("default") or {}).get("url")
                subscriptions.append(
                    {
                        "channel_id": channel_id,
                        "title": snippet.get("title") or channel_id,
                        "description": snippet.get("description") or "",
                        "thumbnail_url": thumbnail,
                        "subscribed_at": snippet.get("publishedAt"),
                    }
                )
            page_token = payload.get("nextPageToken")
            if not page_token:
                return subscriptions

    async def fetch_rss(self, channel_id: str) -> list[dict[str, Any]]:
        response = await (await self._client()).get(RSS_BASE, params={"channel_id": channel_id})
        if response.status_code >= 400:
            raise YouTubeApiError(
                f"RSS request failed ({response.status_code})", status_code=response.status_code
            )
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError as exc:
            raise YouTubeApiError("YouTube RSS returned invalid XML") from exc
        ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
        entries: list[dict[str, Any]] = []
        for entry in root.findall("atom:entry", ns):
            video_id = entry.findtext("yt:videoId", default="", namespaces=ns).strip()
            if not video_id:
                continue
            title = html.unescape(entry.findtext("atom:title", default=video_id, namespaces=ns))
            channel_title = entry.findtext("atom:author/atom:name", default="", namespaces=ns)
            published_at = entry.findtext("atom:published", default="", namespaces=ns)
            updated_at = entry.findtext("atom:updated", default=published_at, namespaces=ns)
            entries.append(
                {
                    "video_id": video_id,
                    "channel_id": channel_id,
                    "channel_title": channel_title,
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "published_at": published_at,
                    "updated_at": updated_at,
                    "published_ts": _published_ts(published_at),
                }
            )
        return entries

    async def fetch_caption(self, video_id: str) -> CaptionResult:
        errors: list[str] = []
        try:
            tracks = await self._api_caption_tracks(video_id)
            if tracks:
                for track in sorted(tracks, key=lambda item: _caption_rank(item["language_code"], item["track_kind"])):
                    try:
                        body = await self._download_caption(track["id"])
                    except YouTubeClientError as exc:
                        errors.append(str(exc))
                        continue
                    if body.strip():
                        return CaptionResult(
                            language_code=track["language_code"],
                            language_name=track["language_name"],
                            track_kind=track["track_kind"],
                            source="youtube_api",
                            body=body,
                        )
        except YouTubeClientError as exc:
            errors.append(str(exc))

        try:
            result = await self._transcript_api_caption(video_id)
            if result:
                return result
        except Exception as exc:  # optional dependency has several release shapes
            errors.append(str(exc))

        detail = "; ".join(dict.fromkeys(errors))
        raise CaptionUnavailable(detail or "No accessible captions were found.")

    async def _api_caption_tracks(self, video_id: str) -> list[dict[str, Any]]:
        payload = await self.api_json("/captions", {"part": "snippet", "videoId": video_id})
        tracks: list[dict[str, Any]] = []
        for item in payload.get("items") or []:
            snippet = item.get("snippet") or {}
            tracks.append(
                {
                    "id": item.get("id"),
                    "language_code": snippet.get("language", ""),
                    "language_name": snippet.get("name", ""),
                    "track_kind": snippet.get("trackKind", "standard"),
                }
            )
        return [track for track in tracks if track.get("id") and track.get("language_code")]

    async def _download_caption(self, caption_id: str) -> str:
        payload = await self.api_text(f"/captions/{caption_id}", {"tfmt": "vtt"})
        return _strip_vtt(payload)

    async def _transcript_api_caption(self, video_id: str) -> Optional[CaptionResult]:
        def fetch() -> Optional[CaptionResult]:
            from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore[import-not-found]

            api = YouTubeTranscriptApi()
            listing = api.list(video_id)
            tracks = list(listing)
            if not tracks:
                return None

            def track_info(track: Any) -> tuple[str, str, str]:
                language_code = str(getattr(track, "language_code", ""))
                language_name = str(getattr(track, "language", ""))
                generated = bool(getattr(track, "is_generated", False))
                return language_code, language_name, "ASR" if generated else "standard"

            tracks.sort(
                key=lambda track: _caption_rank(track_info(track)[0], track_info(track)[2])
            )
            track = tracks[0]
            language_code, language_name, track_kind = track_info(track)
            fetched = track.fetch()
            chunks: list[str] = []
            for item in fetched:
                text = getattr(item, "text", None)
                if text is None and isinstance(item, dict):
                    text = item.get("text")
                if text:
                    chunks.append(str(text).strip())
            body = "\n\n".join(chunk for chunk in chunks if chunk)
            if not body:
                return None
            return CaptionResult(
                language_code=language_code,
                language_name=language_name,
                track_kind=track_kind,
                source="youtube_transcript_api",
                body=body,
            )

        return await asyncio.to_thread(fetch)

    async def api_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        token = await self.access_token()
        response = await (await self._client()).get(
            API_BASE + path,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        payload = self._json_or_empty(response)
        if response.status_code == 401:
            profile = self.profile()
            profile["needs_authorization"] = True
            self.secrets.put("youtube:default", profile)
            raise YouTubeAuthError("YouTube authorization has expired. Connect YouTube again.")
        if response.status_code >= 400:
            message = ((payload.get("error") or {}).get("message") if isinstance(payload, dict) else None)
            raise YouTubeApiError(
                str(message or f"YouTube API request failed ({response.status_code})"),
                status_code=response.status_code,
                payload=payload,
            )
        return payload

    async def api_text(self, path: str, params: dict[str, Any]) -> str:
        token = await self.access_token()
        response = await (await self._client()).get(
            API_BASE + path,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code == 401:
            profile = self.profile()
            profile["needs_authorization"] = True
            self.secrets.put("youtube:default", profile)
            raise YouTubeAuthError("YouTube authorization has expired. Connect YouTube again.")
        if response.status_code >= 400:
            raise YouTubeApiError(
                f"YouTube caption download failed ({response.status_code})",
                status_code=response.status_code,
            )
        return response.text

    @staticmethod
    def _json_or_empty(response: httpx.Response) -> dict[str, Any]:
        try:
            value = response.json()
        except ValueError:
            return {}
        return value if isinstance(value, dict) else {}


def _strip_vtt(value: str) -> str:
    lines: list[str] = []
    for raw in value.splitlines():
        line = raw.strip()
        if not line or line == "WEBVTT" or line.startswith("NOTE"):
            continue
        if "-->" in line or line.isdigit():
            continue
        lines.append(html.unescape(line))
    return "\n\n".join(lines)
