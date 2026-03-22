"""Tests for session TTL and cleanup."""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.session_store import InMemorySessionStore, SQLiteSessionStore


def _age_session(store, session_id: str, seconds: int) -> None:
    """Backdate a session's created_at by the given number of seconds."""
    if isinstance(store, InMemorySessionStore):
        s = store._sessions[session_id]
        s.created_at = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    elif isinstance(store, SQLiteSessionStore):
        from contracts.models import SessionState

        with store._lock:
            cursor = store._conn.execute(
                "SELECT state_json FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
        session = SessionState.model_validate_json(row[0])
        session.created_at = datetime.now(timezone.utc) - timedelta(seconds=seconds)
        store.save_session(session)


class TestInMemoryTTL:
    def test_fresh_session_returned(self):
        store = InMemorySessionStore(ttl_seconds=3600)
        s = store.create_session()
        assert store.get_session(s.session_id) is not None

    def test_expired_session_returns_none(self):
        store = InMemorySessionStore(ttl_seconds=60)
        s = store.create_session()
        _age_session(store, s.session_id, 120)
        assert store.get_session(s.session_id) is None

    def test_expired_session_removed_from_dict(self):
        store = InMemorySessionStore(ttl_seconds=60)
        s = store.create_session()
        _age_session(store, s.session_id, 120)
        store.get_session(s.session_id)
        assert s.session_id not in store._sessions

    def test_cleanup_expired(self):
        store = InMemorySessionStore(ttl_seconds=60)
        s1 = store.create_session()
        s2 = store.create_session()
        s3 = store.create_session()
        _age_session(store, s1.session_id, 120)
        _age_session(store, s2.session_id, 120)
        removed = store.cleanup_expired()
        assert removed == 2
        assert store.get_session(s3.session_id) is not None

    def test_created_at_set_on_create(self):
        store = InMemorySessionStore()
        s = store.create_session()
        assert s.created_at is not None
        assert (datetime.now(timezone.utc) - s.created_at).total_seconds() < 5


class TestSQLiteTTL:
    @pytest.fixture()
    def store(self, tmp_path):
        return SQLiteSessionStore(str(tmp_path / "test.db"), ttl_seconds=60)

    def test_fresh_session_returned(self, store):
        s = store.create_session()
        assert store.get_session(s.session_id) is not None

    def test_expired_session_returns_none(self, store):
        s = store.create_session()
        _age_session(store, s.session_id, 120)
        assert store.get_session(s.session_id) is None

    def test_expired_session_deleted_from_db(self, store):
        s = store.create_session()
        _age_session(store, s.session_id, 120)
        store.get_session(s.session_id)
        with store._lock:
            cursor = store._conn.execute(
                "SELECT count(*) FROM sessions WHERE session_id = ?",
                (s.session_id,),
            )
            assert cursor.fetchone()[0] == 0

    def test_cleanup_expired(self, store):
        s1 = store.create_session()
        s2 = store.create_session()
        s3 = store.create_session()
        _age_session(store, s1.session_id, 120)
        _age_session(store, s2.session_id, 120)
        removed = store.cleanup_expired()
        assert removed == 2
        assert store.get_session(s3.session_id) is not None

    def test_created_at_persists_through_json(self, store):
        s = store.create_session()
        loaded = store.get_session(s.session_id)
        assert loaded is not None
        assert abs((s.created_at - loaded.created_at).total_seconds()) < 1
