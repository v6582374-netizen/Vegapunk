"""Deterministic YouTube automation run orchestration."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .client import CaptionUnavailable, YouTubeAuthError, YouTubeClient, YouTubeClientError
from .store import YouTubeStore


@dataclass
class YouTubeRunResult:
    discovered: int = 0
    captions_ready: int = 0
    caption_failures: int = 0
    channel_failures: list[str] = field(default_factory=list)
    caption_errors: list[dict[str, str]] = field(default_factory=list)
    scan_started_at: float = 0.0
    scan_finished_at: float = 0.0
    artifact: Optional[str] = None

    @property
    def partial(self) -> bool:
        return bool(self.channel_failures or self.caption_failures)

    def result_text(self) -> str:
        status = "completed with warnings" if self.partial else "completed"
        lines = [
            f"YouTube update scan {status}.",
            f"Discovered {self.discovered} new video(s); {self.captions_ready} caption(s) ready.",
        ]
        if self.caption_failures:
            lines.append(f"{self.caption_failures} video(s) had no accessible caption yet.")
        if self.channel_failures:
            lines.append(f"{len(self.channel_failures)} channel(s) could not be scanned; the cursor was kept for retry.")
        return "\n".join(lines)


class YouTubeAutomationService:
    """Run one daily task without an LLM in the critical path."""

    def __init__(self, store: YouTubeStore, client: YouTubeClient) -> None:
        self.store = store
        self.client = client

    async def sync_subscriptions(self) -> dict[str, Any]:
        channels = await self.client.list_subscriptions()
        count = self.store.replace_channels(channels)
        self.store.set_state("subscriptions_synced_at", time.time())
        return {"ok": True, "count": count, "channels": self.store.list_channels()}

    async def run(
        self,
        *,
        task_id: str,
        workspace: str | Path,
        now: Optional[float] = None,
    ) -> YouTubeRunResult:
        result = YouTubeRunResult(scan_started_at=time.time())
        now = float(now if now is not None else time.time())
        authorized_at = self.store.get_state("authorized_at")
        last_scan = self.store.get_state("last_scan_at")
        cursor = float(last_scan or authorized_at or 0.0)
        channels = self.store.list_channels()
        if not channels:
            await self.sync_subscriptions()
            channels = self.store.list_channels()
        # A small overlap prevents a timestamp boundary from dropping an entry. video_id makes
        # the overlap idempotent.
        since = max(0.0, cursor - 300.0)
        all_candidates: list[dict[str, Any]] = []
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
                    all_candidates.append(entry)

        # Retry caption failures from previous runs as well as newly discovered videos. This
        # means a transient subtitle endpoint failure does not become permanent just because RSS
        # discovery has already advanced.
        retry_candidates = [
            video
            for video in self.store.list_videos()
            if video.get("caption_status") in {"pending", "error"}
            and video.get("video_id") not in {v.get("video_id") for v in all_candidates}
        ]
        candidates = all_candidates + retry_candidates
        result.discovered = len(all_candidates)
        for video in candidates:
            try:
                caption = await self.client.fetch_caption(video["video_id"])
                self.store.set_caption(
                    video["video_id"],
                    language_code=caption.language_code,
                    language_name=caption.language_name,
                    track_kind=caption.track_kind,
                    source=caption.source,
                    body=caption.body,
                )
                result.captions_ready += 1
            except CaptionUnavailable as exc:
                result.caption_failures += 1
                message = str(exc) or "No accessible captions were found."
                self.store.set_caption_error(video["video_id"], message)
                result.caption_errors.append({"video_id": video["video_id"], "error": message})
            except YouTubeAuthError:
                # A revoked token invalidates the whole run, not just one video.
                raise
            except YouTubeClientError as exc:
                result.caption_failures += 1
                message = str(exc) or "Caption fetch failed."
                self.store.set_caption_error(video["video_id"], message)
                result.caption_errors.append({"video_id": video["video_id"], "error": message})

        result.scan_finished_at = time.time()
        if not result.channel_failures:
            self.store.set_state("last_scan_at", now)
        result.artifact = self._write_run_artifact(workspace, task_id, result)
        return result

    def _write_run_artifact(
        self, workspace: str | Path, task_id: str, result: YouTubeRunResult
    ) -> Optional[str]:
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
                        "captions_ready": result.captions_ready,
                        "caption_failures": result.caption_errors,
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
