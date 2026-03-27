"""End-to-end tests for Bland AI tool endpoints."""

from __future__ import annotations

import pytest

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ModuleNotFoundError:
    FastAPI = None
    TestClient = None

from api import app as api_app
from api.app import create_app
from tests.conftest import make_service


def _make_client(monkeypatch, intent: str) -> TestClient:
    service = make_service(monkeypatch, intent)
    api_app._SERVICE = service
    return TestClient(create_app())


@pytest.mark.skipif(FastAPI is None, reason="FastAPI not installed")
class TestBlandToolStartSession:
    def test_returns_greeting_and_session_id(self, monkeypatch):
        client = _make_client(monkeypatch, "password_reset")
        resp = client.post(
            "/bland/tool/start-session",
            json={"call_id": "bland-call-1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "bland-call-1"
        assert data["message"] == "Hello! How can I help you today?"
        assert data["resolved"] is False
        assert data["escalated"] is False


@pytest.mark.skipif(FastAPI is None, reason="FastAPI not installed")
class TestBlandToolHandleBusinessTurn:
    def test_password_reset_happy_path(self, monkeypatch):
        client = _make_client(monkeypatch, "password_reset")

        # Start session
        client.post("/bland/tool/start-session", json={"call_id": "bland-pw-1"})

        # Route intent
        r1 = client.post(
            "/bland/tool/handle-business-turn",
            json={"call_id": "bland-pw-1", "utterance": "I need to reset my password"},
        )
        assert r1.status_code == 200
        assert r1.json()["resolved"] is False

        # Provide both fields
        r2 = client.post(
            "/bland/tool/handle-business-turn",
            json={"call_id": "bland-pw-1", "utterance": "12345678 654321"},
        )
        assert r2.status_code == 200
        assert r2.json()["resolved"] is True

    def test_escalation_on_human_request(self, monkeypatch):
        client = _make_client(monkeypatch, "password_reset")

        client.post("/bland/tool/start-session", json={"call_id": "bland-esc-1"})
        client.post(
            "/bland/tool/handle-business-turn",
            json={"call_id": "bland-esc-1", "utterance": "I can't log in"},
        )

        r2 = client.post(
            "/bland/tool/handle-business-turn",
            json={"call_id": "bland-esc-1", "utterance": "let me speak to a human"},
        )
        assert r2.status_code == 200
        assert r2.json()["escalated"] is True

    def test_numeric_input_as_text(self, monkeypatch):
        """Numeric input submitted as text utterance (replaces old DTMF tests)."""
        client = _make_client(monkeypatch, "password_reset")

        client.post("/bland/tool/start-session", json={"call_id": "bland-num-1"})
        client.post(
            "/bland/tool/handle-business-turn",
            json={"call_id": "bland-num-1", "utterance": "I need to reset my password"},
        )

        r2 = client.post(
            "/bland/tool/handle-business-turn",
            json={"call_id": "bland-num-1", "utterance": "12345678"},
        )
        assert r2.status_code == 200
        assert r2.json()["resolved"] is False
        assert "verification" in r2.json()["message"].lower()


@pytest.mark.skipif(FastAPI is None, reason="FastAPI not installed")
class TestBlandWebhook:
    def test_webhook_returns_ok(self, monkeypatch):
        client = _make_client(monkeypatch, "password_reset")
        resp = client.post(
            "/bland/webhook",
            json={"status": "completed", "call_id": "bland-wh-1"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_webhook_accepts_in_progress(self, monkeypatch):
        client = _make_client(monkeypatch, "password_reset")
        resp = client.post(
            "/bland/webhook",
            json={"status": "in-progress", "call_id": "bland-wh-2"},
        )
        assert resp.status_code == 200


@pytest.mark.skipif(FastAPI is None, reason="FastAPI not installed")
class TestBlandEndpointValidation:
    def test_voice_event_endpoint_gone(self, monkeypatch):
        """The old /voice-event endpoint should no longer exist."""
        client = _make_client(monkeypatch, "password_reset")
        resp = client.post("/voice-event", json={"type": "transcript"})
        assert resp.status_code in {404, 405}

    def test_twilio_stream_endpoint_gone(self, monkeypatch):
        """The old /ws/twilio-stream endpoint should no longer exist."""
        client = _make_client(monkeypatch, "password_reset")
        resp = client.get("/ws/twilio-stream")
        assert resp.status_code in {404, 403}
