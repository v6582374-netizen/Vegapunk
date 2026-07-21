"""Local administrator authentication and session storage.

The first product version has one local administrator rather than a user
directory.  This module keeps that deliberately small interface while hiding
password hashing, session expiry, and SQLite persistence behind it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin"
SESSION_COOKIE_NAME = "vegapunk_admin_session"
SESSION_IDLE_SECONDS = 12 * 60 * 60
SESSION_ABSOLUTE_SECONDS = 7 * 24 * 60 * 60


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("ascii"))


def _hash_password(password: str, salt: bytes | None = None) -> str:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=actual_salt,
        n=2**14,
        r=8,
        p=1,
    )
    return f"scrypt$16384$8$1${_encode(actual_salt)}${_encode(digest)}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, encoded_salt, encoded_digest = encoded.split("$")
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_decode(encoded_salt),
            n=int(n),
            r=int(r),
            p=int(p),
        )
        return hmac.compare_digest(digest, _decode(encoded_digest))
    except (ValueError, TypeError):
        return False


class AdminAuth:
    """Authenticate the single local administrator and manage sessions."""

    cookie_name = SESSION_COOKIE_NAME

    def __init__(
        self,
        database_path: Path,
        *,
        password: str | None = None,
        clock: Callable[[], float] = time.time,
        idle_seconds: int = SESSION_IDLE_SECONDS,
        absolute_seconds: int = SESSION_ABSOLUTE_SECONDS,
    ) -> None:
        self.database_path = database_path
        self._clock = clock
        self.idle_seconds = idle_seconds
        self.absolute_seconds = absolute_seconds
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.database_path.exists():
            self.database_path.touch(mode=0o600)
        self.database_path.chmod(0o600)
        self._initialize(password)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @contextmanager
    def _connection(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self, password: str | None) -> None:
        configured_password = password or os.environ.get(
            "VEGAPUNK_ADMIN_PASSWORD", DEFAULT_ADMIN_PASSWORD
        )
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS admin_credentials (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS admin_sessions (
                    session_hash TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO admin_credentials(username, password_hash)
                VALUES (?, ?)
                """,
                (DEFAULT_ADMIN_USERNAME, _hash_password(configured_password)),
            )

    @staticmethod
    def _session_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def login(self, username: str, password: str) -> str | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT password_hash FROM admin_credentials WHERE username = ?",
                (username,),
            ).fetchone()
        if row is None or not _verify_password(password, row[0]):
            return None

        now = self._clock()
        token = secrets.token_urlsafe(32)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO admin_sessions(
                    session_hash, username, created_at, last_seen_at, expires_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    self._session_hash(token),
                    username,
                    now,
                    now,
                    now + self.absolute_seconds,
                ),
            )
        return token

    def session_username(self, token: str | None) -> str | None:
        if not token:
            return None
        now = self._clock()
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT username, created_at, last_seen_at, expires_at
                FROM admin_sessions
                WHERE session_hash = ?
                """,
                (self._session_hash(token),),
            ).fetchone()
            if row is None:
                return None
            username, created_at, last_seen_at, expires_at = row
            if now >= expires_at or now - last_seen_at >= self.idle_seconds:
                connection.execute(
                    "DELETE FROM admin_sessions WHERE session_hash = ?",
                    (self._session_hash(token),),
                )
                return None
            connection.execute(
                "UPDATE admin_sessions SET last_seen_at = ? WHERE session_hash = ?",
                (now, self._session_hash(token)),
            )
            if now >= created_at + self.absolute_seconds:
                connection.execute(
                    "DELETE FROM admin_sessions WHERE session_hash = ?",
                    (self._session_hash(token),),
                )
                return None
            return username

    def logout(self, token: str | None) -> None:
        if not token:
            return
        with self._connection() as connection:
            connection.execute(
                "DELETE FROM admin_sessions WHERE session_hash = ?",
                (self._session_hash(token),),
            )
