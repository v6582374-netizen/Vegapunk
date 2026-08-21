"""Deterministic YouTube library update orchestration."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .client import (
    CaptionUnavailable,
    YouTubeAuthError,
    YouTubeClient,
    YouTubeClientError,
)
from .store import YouTubeStore


@dataclass
class YouTubeRunResult:
    discovered: int = 0
    channel_failures: list[str] = field(default_factory=list)
    scan_started_at: float = 0.0
    scan_finished_at: float = 0.0
    artifact: str | None = None

    @property
    def partial(self) -> bool:
        return bool(self.channel_failures)

    def result_text(self) -> str:
        status = "completed with warnings" if self.partial else "completed"
        lines = [
            f"YouTube update scan {status}.",
            f"Discovered {self.discovered} new video(s).",
        ]
        if self.channel_failures:
            lines.append(f"{len(self.channel_failures)} channel(s) could not be scanned; the cursor was kept for retry.")
        return "\n".join(lines)


class YouTubeAutomationService:
    """Keep the local YouTube library aligned with the connected account."""

    def __init__(self, store: YouTubeStore, client: YouTubeClient) -> None:
        self.store = store
        self.client = client

    async def sync_subscriptions(self) -> dict[str, Any]:
        channels = await self.client.list_subscriptions()
        count = self.store.replace_channels(channels)
        self.store.prune_unsubscribed_unprocessed_videos()
        self.store.set_state("subscriptions_synced_at", time.time())
        return {"ok": True, "count": count, "channels": self.store.list_channels()}

    async def scan(self, *, now: float | None = None) -> YouTubeRunResult:
        """Refresh subscriptions and discover new videos on demand.

        Scanning is the domain operation.  A scheduled task, if an older installation still
        has one, is only one possible caller; the library does not depend on a scheduler.
        """
        result = YouTubeRunResult(scan_started_at=time.time())
        now = float(now if now is not None else time.time())
        authorized_at = self.store.get_state("authorized_at")
        last_scan = self.store.get_state("last_scan_at")
        cursor = float(last_scan or authorized_at or 0.0)
        # RSS is public, but a run is not allowed to proceed without a valid OAuth
        # grant.  Failing before discovery prevents an expired token from advancing
        # the local cursor and makes the task visibly recoverable by re-authorizing.
        await self.client.ensure_authorized()
        # The subscription snapshot is authoritative only for one scan. Refreshing it
        # every time prevents unsubscribed channels from lingering in future RSS polls.
        await self.sync_subscriptions()
        channels = self.store.list_channels()
        # A small overlap prevents a timestamp boundary from dropping an entry. video_id makes
        # the overlap idempotent.
        since = max(0.0, cursor - 300.0)
        discovered = 0
        for channel in channels:
            channel_id = channel["channel_id"]
            try:
                entries = await self.client.fetch_rss(channel_id)
            except YouTubeClientError as exc:
                result.channel_failures.append(f"{channel.get('title') or channel_id}: {exc}")
                continue
            for entry in entries:
                published_ts = entry.get("published_ts")
                if published_ts is not None and not (since < float(published_ts) <= now):
                    continue
                entry["channel_title"] = channel.get("title") or entry.get("channel_title") or channel_id
                entry["discovered_at"] = result.scan_started_at
                if self.store.upsert_video(entry):
                    discovered += 1

        result.discovered = discovered

        result.scan_finished_at = time.time()
        if not result.channel_failures:
            self.store.set_state("last_scan_at", now)
        return result

    async def fetch_caption(self, video_id: str) -> dict[str, Any]:
        """Fetch the best available caption for one video chosen by the user."""
        if self.store.get_video(video_id) is None:
            raise KeyError(video_id)
        try:
            caption = await self.client.fetch_caption(video_id)
        except YouTubeAuthError:
            # Authorization is an account-level failure and should not be persisted as
            # evidence that this particular video has no caption.
            raise
        except (CaptionUnavailable, YouTubeClientError) as exc:
            message = str(exc) or "No accessible captions were found."
            self.store.set_caption_error(video_id, message)
            return {
                "ok": False,
                "error": message,
                "video": self.store.get_video(video_id),
            }

        self.store.set_caption(
            video_id,
            language_code=caption.language_code,
            language_name=caption.language_name,
            track_kind=caption.track_kind,
            source=caption.source,
            body=caption.body,
        )
        return {"ok": True, "video": self.store.get_video(video_id)}

    async def run(
        self,
        *,
        task_id: str,
        workspace: str | Path,
        now: float | None = None,
    ) -> YouTubeRunResult:
        """Legacy scheduled-task adapter; new UI work calls :meth:`scan` directly."""
        result = await self.scan(now=now)
        result.artifact = self._write_run_artifact(workspace, task_id, result)
        return result

    def _write_run_artifact(
        self, workspace: str | Path, task_id: str, result: YouTubeRunResult
    ) -> str | None:
        try:
            root = Path(workspace)
            root.mkdir(parents=True, exist_ok=True)
            filename = f"youtube-run-{int(result.scan_finished_at or time.time())}.json"
            path = root / filename
            path.write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "scan_started_at": result.scan_started_at,
                        "scan_finished_at": result.scan_finished_at,
                        "discovered": result.discovered,
                        "channel_failures": result.channel_failures,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            return filename
        except OSError:
            return None
