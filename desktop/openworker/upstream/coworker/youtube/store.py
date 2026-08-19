"""Local SQLite state for the single-user YouTube automation."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Optional


def _now() -> float:
    return time.time()


class YouTubeStore:
    """Persist YouTube state without putting catalog data in the secret store.

    The secret store is reserved for OAuth credentials.  This database contains the local
    subscription snapshot, discovered videos, one chosen raw caption per video, and the
    user's future-translation selection.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS youtube_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS youtube_channels (
                    channel_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    thumbnail_url TEXT,
                    subscribed_at TEXT,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS youtube_videos (
                    video_id TEXT PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    channel_title TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    published_ts REAL,
                    discovered_at REAL NOT NULL,
                    selected INTEGER NOT NULL DEFAULT 0,
                    caption_status TEXT NOT NULL DEFAULT 'pending',
                    caption_error TEXT,
                    deleted_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_youtube_videos_published
                    ON youtube_videos(published_ts DESC);
                CREATE INDEX IF NOT EXISTS idx_youtube_videos_selected
                    ON youtube_videos(selected, deleted_at);
                CREATE TABLE IF NOT EXISTS youtube_captions (
                    video_id TEXT PRIMARY KEY,
                    language_code TEXT NOT NULL,
                    language_name TEXT NOT NULL DEFAULT '',
                    track_kind TEXT NOT NULL DEFAULT 'standard',
                    source TEXT NOT NULL,
                    body TEXT NOT NULL,
                    fetched_at REAL NOT NULL,
                    FOREIGN KEY(video_id) REFERENCES youtube_videos(video_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS youtube_deleted_videos (
                    video_id TEXT PRIMARY KEY,
                    deleted_at REAL NOT NULL
                );
                """
            )
            self._conn.commit()

    # -- generic state -----------------------------------------------------
    def get_state(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM youtube_state WHERE key=?", (key,)
            ).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except (TypeError, json.JSONDecodeError):
            return default

    def set_state(self, key: str, value: Any) -> None:
        encoded = json.dumps(value)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO youtube_state(key, value) VALUES (?, ?)",
                (key, encoded),
            )
            self._conn.commit()

    # -- subscriptions -----------------------------------------------------
    def replace_channels(self, channels: Iterable[dict[str, Any]]) -> int:
        rows = list(channels)
        now = _now()
        with self._lock:
            self._conn.execute("DELETE FROM youtube_channels")
            self._conn.executemany(
                """
                INSERT INTO youtube_channels
                    (channel_id, title, description, thumbnail_url, subscribed_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(c["channel_id"]),
                        str(c.get("title") or c["channel_id"]),
                        str(c.get("description") or ""),
                        c.get("thumbnail_url"),
                        c.get("subscribed_at"),
                        now,
                    )
                    for c in rows
                    if c.get("channel_id")
                ],
            )
            self._conn.commit()
        return len(rows)

    def list_channels(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM youtube_channels ORDER BY title COLLATE NOCASE"
            ).fetchall()
        return [dict(row) for row in rows]

    # -- videos ------------------------------------------------------------
    def upsert_video(self, video: dict[str, Any]) -> bool:
        video_id = str(video.get("video_id") or "").strip()
        if not video_id:
            return False
        with self._lock:
            if self._conn.execute(
                "SELECT 1 FROM youtube_deleted_videos WHERE video_id=?", (video_id,)
            ).fetchone():
                return False
            existing = self._conn.execute(
                "SELECT 1 FROM youtube_videos WHERE video_id=?", (video_id,)
            ).fetchone()
            self._conn.execute(
                """
                INSERT INTO youtube_videos
                    (video_id, channel_id, channel_title, title, url, published_at, published_ts,
                     discovered_at, selected, caption_status, caption_error, deleted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 'pending', NULL, NULL)
                ON CONFLICT(video_id) DO UPDATE SET
                    channel_id=excluded.channel_id,
                    channel_title=excluded.channel_title,
                    title=excluded.title,
                    url=excluded.url,
                    published_at=excluded.published_at,
                    published_ts=excluded.published_ts
                """,
                (
                    video_id,
                    str(video.get("channel_id") or ""),
                    str(video.get("channel_title") or ""),
                    str(video.get("title") or video_id),
                    str(video.get("url") or f"https://www.youtube.com/watch?v={video_id}"),
                    str(video.get("published_at") or ""),
                    video.get("published_ts"),
                    float(video.get("discovered_at") or _now()),
                ),
            )
            self._conn.commit()
        return existing is None

    def list_videos(self, *, include_deleted: bool = False) -> list[dict[str, Any]]:
        where = "" if include_deleted else "WHERE v.deleted_at IS NULL"
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT v.*, c.language_code, c.language_name, c.track_kind, c.source AS caption_source,
                       c.body AS caption_body
                FROM youtube_videos v
                LEFT JOIN youtube_captions c ON c.video_id = v.video_id
                {where}
                ORDER BY COALESCE(v.published_ts, 0) DESC, v.discovered_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_video(self, video_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT v.*, c.language_code, c.language_name, c.track_kind,
                       c.source AS caption_source, c.body AS caption_body
                FROM youtube_videos v
                LEFT JOIN youtube_captions c ON c.video_id=v.video_id
                WHERE v.video_id=? AND v.deleted_at IS NULL
                """,
                (video_id,),
            ).fetchone()
        return dict(row) if row else None

    def set_selected(self, video_id: str, selected: bool) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE youtube_videos SET selected=? WHERE video_id=? AND deleted_at IS NULL",
                (1 if selected else 0, video_id),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def set_caption(
        self,
        video_id: str,
        *,
        language_code: str,
        language_name: str,
        track_kind: str,
        source: str,
        body: str,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO youtube_captions
                    (video_id, language_code, language_name, track_kind, source, body, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (video_id, language_code, language_name, track_kind, source, body, _now()),
            )
            self._conn.execute(
                "UPDATE youtube_videos SET caption_status='ready', caption_error=NULL WHERE video_id=?",
                (video_id,),
            )
            self._conn.commit()

    def set_caption_error(self, video_id: str, error: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE youtube_videos SET caption_status='error', caption_error=? WHERE video_id=?",
                (error[:1000], video_id),
            )
            self._conn.commit()

    def delete_video(self, video_id: str) -> bool:
        now = _now()
        with self._lock:
            exists = self._conn.execute(
                "SELECT 1 FROM youtube_videos WHERE video_id=? AND deleted_at IS NULL",
                (video_id,),
            ).fetchone()
            if not exists:
                return False
            self._conn.execute(
                "INSERT OR REPLACE INTO youtube_deleted_videos(video_id, deleted_at) VALUES (?, ?)",
                (video_id, now),
            )
            self._conn.execute("DELETE FROM youtube_captions WHERE video_id=?", (video_id,))
            self._conn.execute("DELETE FROM youtube_videos WHERE video_id=?", (video_id,))
            self._conn.commit()
        return True

    def close(self) -> None:
        with self._lock:
            self._conn.close()
