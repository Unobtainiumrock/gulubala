"""Session persistence backends."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from contracts.models import SessionState


class SessionStore(Protocol):
    def create_session(self, channel: str = "text", session_id: str | None = None) -> SessionState:
        raise NotImplementedError

    def get_session(self, session_id: str) -> SessionState | None:
        raise NotImplementedError

    def save_session(self, session: SessionState) -> SessionState:
        raise NotImplementedError


class InMemorySessionStore:
    """Simple session store used by the CLI and tests."""

    def __init__(self):
        self._sessions: dict[str, SessionState] = {}

    def create_session(self, channel: str = "text", session_id: str | None = None) -> SessionState:
        session = SessionState(channel=channel, session_id=session_id or uuid4().hex)
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> SessionState | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        return SessionState.model_validate(session.model_dump())

    def save_session(self, session: SessionState) -> SessionState:
        self._sessions[session.session_id] = SessionState.model_validate(session.model_dump())
        return session


class SQLiteSessionStore:
    """SQLite-backed session store used by the API surface."""

    def __init__(self, path: str):
        self.path = path
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
        cursor = self._conn.execute(
            "SELECT state_json FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return SessionState.model_validate_json(row[0])

    def save_session(self, session: SessionState) -> SessionState:
        timestamp = datetime.now(timezone.utc).isoformat()
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
