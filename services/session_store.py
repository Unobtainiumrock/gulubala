"""Session persistence backends."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from config.models import SESSION_TTL_SECONDS
from contracts.models import SessionState


class SessionStore(Protocol):
    def create_session(self, channel: str = "text", session_id: str | None = None) -> SessionState:
        raise NotImplementedError

    def get_session(self, session_id: str) -> SessionState | None:
        raise NotImplementedError

    def save_session(self, session: SessionState) -> SessionState:
        raise NotImplementedError

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count of sessions removed."""
        raise NotImplementedError


def _is_expired(session: SessionState, ttl: int) -> bool:
    age = (datetime.now(timezone.utc) - session.created_at).total_seconds()
    return age > ttl


class InMemorySessionStore:
    """Simple session store used by the CLI and tests."""

    def __init__(self, ttl_seconds: int = SESSION_TTL_SECONDS):
        self._sessions: dict[str, SessionState] = {}
        self._ttl = ttl_seconds

    def create_session(self, channel: str = "text", session_id: str | None = None) -> SessionState:
        session = SessionState(channel=channel, session_id=session_id or uuid4().hex)
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> SessionState | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if _is_expired(session, self._ttl):
            del self._sessions[session_id]
            return None
        return SessionState.model_validate(session.model_dump())

    def save_session(self, session: SessionState) -> SessionState:
        self._sessions[session.session_id] = SessionState.model_validate(session.model_dump())
        return session

    def cleanup_expired(self) -> int:
        expired = [sid for sid, s in self._sessions.items() if _is_expired(s, self._ttl)]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)


class SQLiteSessionStore:
    """SQLite-backed session store used by the API surface."""

    def __init__(self, path: str, ttl_seconds: int = SESSION_TTL_SECONDS):
        self.path = path
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
        db_path = Path(path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def create_session(self, channel: str = "text", session_id: str | None = None) -> SessionState:
        session = SessionState(channel=channel, session_id=session_id or uuid4().hex)
        return self.save_session(session)

    def get_session(self, session_id: str) -> SessionState | None:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT state_json FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        session = SessionState.model_validate_json(row[0])
        if _is_expired(session, self._ttl):
            self._delete_session(session_id)
            return None
        return session

    def save_session(self, session: SessionState) -> SessionState:
        timestamp = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO sessions (session_id, state_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                  state_json = excluded.state_json,
                  updated_at = excluded.updated_at
                """,
                (session.session_id, session.model_dump_json(), timestamp),
            )
            self._conn.commit()
        return session

    def cleanup_expired(self) -> int:
        cutoff = datetime.now(timezone.utc).isoformat()
        with self._lock:
            # Fetch all sessions and check TTL against created_at in the JSON
            cursor = self._conn.execute("SELECT session_id, state_json FROM sessions")
            expired_ids = []
            for row in cursor.fetchall():
                session = SessionState.model_validate_json(row[1])
                if _is_expired(session, self._ttl):
                    expired_ids.append(row[0])
            if expired_ids:
                placeholders = ",".join("?" for _ in expired_ids)
                self._conn.execute(
                    f"DELETE FROM sessions WHERE session_id IN ({placeholders})",
                    expired_ids,
                )
                self._conn.commit()
        return len(expired_ids)

    def _delete_session(self, session_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            self._conn.commit()
