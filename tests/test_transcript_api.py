"""Tests for IVR navigator transcript HTTP API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import create_app
from calltree.transcript_store import clear_transcript, record_transcript_turn


def test_transcript_404_when_missing() -> None:
    app = create_app()
    client = TestClient(app)
    r = client.get("/transcript/nonexistent-session")
    assert r.status_code == 404


def test_transcript_returns_lines() -> None:
    app = create_app()
    client = TestClient(app)
    sid = "demo-session-1"
    clear_transcript(sid)
    record_transcript_turn(sid, "ivr", "Press 1 for billing")
    record_transcript_turn(sid, "agent", "[DTMF: 1]")
    try:
        r = client.get(f"/transcript/{sid}")
        assert r.status_code == 200
        data = r.json()
        assert data["session_id"] == sid
        assert len(data["lines"]) == 2
        assert data["lines"][0]["role"] == "ivr"
    finally:
        clear_transcript(sid)
