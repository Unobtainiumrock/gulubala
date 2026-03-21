"""DEV-15: End-to-end voice integration tests via /voice-event."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_service

import api.app as app_mod


def _make_client(monkeypatch: pytest.MonkeyPatch, intent: str) -> TestClient:
    """Build a TestClient backed by a stubbed CallCenterService."""
    service = make_service(monkeypatch, intent)
    app_mod._SERVICE = service
    return TestClient(app_mod.create_app())


class TestPasswordResetVoiceFlow:
    """Full password_reset through transcript events on /voice-event."""

    def test_happy_path(self, monkeypatch):
        client = _make_client(monkeypatch, "password_reset")

        r1 = client.post("/voice-event", json={
            "type": "transcript",
            "session_id": "pw-voice-1",
            "text": "I need to reset my password",
        })
        assert r1.status_code == 200
        data1 = r1.json()
        assert data1["session_id"] == "pw-voice-1"
        assert data1["resolved"] is False
        assert data1["escalated"] is False

        r2 = client.post("/voice-event", json={
            "type": "transcript",
            "session_id": "pw-voice-1",
            "text": "12345678 654321",
        })
        assert r2.status_code == 200
        data2 = r2.json()
        assert data2["resolved"] is True
        assert "Password reset initiated" in data2["message"]

    def test_dtmf_account_id(self, monkeypatch):
        client = _make_client(monkeypatch, "password_reset")

        client.post("/voice-event", json={
            "type": "transcript",
            "session_id": "pw-dtmf-1",
            "text": "I can't log in",
        })

        r2 = client.post("/voice-event", json={
            "type": "dtmf",
            "session_id": "pw-dtmf-1",
            "digits": "12345678",
        })
        assert r2.status_code == 200
        data2 = r2.json()
        assert data2["resolved"] is False
        assert data2["escalated"] is False

        r3 = client.post("/voice-event", json={
            "type": "transcript",
            "session_id": "pw-dtmf-1",
            "text": "654321",
        })
        assert r3.status_code == 200
        assert r3.json()["resolved"] is True

    def test_escalation_on_human_request(self, monkeypatch):
        client = _make_client(monkeypatch, "password_reset")

        client.post("/voice-event", json={
            "type": "transcript",
            "session_id": "pw-esc-1",
            "text": "I need to reset my password",
        })

        r2 = client.post("/voice-event", json={
            "type": "transcript",
            "session_id": "pw-esc-1",
            "text": "let me speak to a human",
        })
        assert r2.status_code == 200
        assert r2.json()["escalated"] is True


class TestBillingDisputeVoiceFlow:
    """Full billing_dispute through transcript events on /voice-event."""

    def test_happy_path(self, monkeypatch):
        client = _make_client(monkeypatch, "billing_dispute")

        r1 = client.post("/voice-event", json={
            "type": "transcript",
            "session_id": "bill-voice-1",
            "text": "I want to dispute a charge on my account",
        })
        assert r1.status_code == 200
        assert r1.json()["resolved"] is False

        r2 = client.post("/voice-event", json={
            "type": "transcript",
            "session_id": "bill-voice-1",
            "text": "12345678 03/01/2026 $95.00",
        })
        assert r2.status_code == 200
        assert r2.json()["resolved"] is True
        assert "Dispute case opened" in r2.json()["message"]


class TestInterruptEvent:
    """Interrupt events preserve session state."""

    def test_interrupt_returns_200(self, monkeypatch):
        client = _make_client(monkeypatch, "password_reset")

        client.post("/voice-event", json={
            "type": "transcript",
            "session_id": "int-1",
            "text": "I can't log in",
        })

        r = client.post("/voice-event", json={
            "type": "interrupt",
            "session_id": "int-1",
        })
        assert r.status_code == 200
        assert r.json()["message"] == "Interruption registered."
        assert r.json()["resolved"] is False


class TestASRWiring:
    """When audio_data is sent, ASR runs before the voice handler."""

    def test_audio_data_triggers_transcription(self, monkeypatch):
        client = _make_client(monkeypatch, "password_reset")

        monkeypatch.setattr(
            "api.app.transcribe",
            lambda chunks: "I need to reset my password",
            raising=False,
        )
        from asr import transcribe as asr_mod
        monkeypatch.setattr(asr_mod, "transcribe", lambda chunks: "I need to reset my password")
        import importlib
        monkeypatch.setattr(
            "asr.transcribe.transcribe",
            lambda chunks: "I need to reset my password",
        )

        r = client.post("/voice-event", json={
            "type": "transcript",
            "session_id": "asr-1",
            "audio_data": "AAAA",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["session_id"] == "asr-1"
        assert data["resolved"] is False


class TestErrorHandling:
    """Edge cases and error responses from /voice-event."""

    def test_missing_session_id_returns_422(self, monkeypatch):
        client = _make_client(monkeypatch, "password_reset")
        r = client.post("/voice-event", json={"type": "transcript"})
        assert r.status_code == 422

    def test_unsupported_event_type_returns_422(self, monkeypatch):
        client = _make_client(monkeypatch, "password_reset")
        r = client.post("/voice-event", json={
            "type": "unknown_type",
            "session_id": "err-1",
        })
        assert r.status_code == 422
