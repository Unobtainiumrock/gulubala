"""HTTP API end-to-end tests for all 5 workflows + negative paths.

Each test exercises a full round-trip through the FastAPI endpoints using
stubbed LLM services (no real API key required).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import api.app as app_mod
from api.app import create_app
from tests.conftest import make_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client_for(monkeypatch: pytest.MonkeyPatch, intent: str) -> TestClient:
    service = make_service(monkeypatch, intent)
    app_mod._SERVICE = service
    return TestClient(create_app())


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_returns_ok(self, monkeypatch):
        client = _client_for(monkeypatch, "password_reset")
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Password Reset – full HTTP flow
# ---------------------------------------------------------------------------


class TestPasswordResetHTTP:
    def test_full_flow(self, monkeypatch):
        client = _client_for(monkeypatch, "password_reset")
        sid = "pw-http-1"

        route = client.post(
            "/route-intent", json={"session_id": sid, "utterance": "I can't log in."}
        )
        assert route.status_code == 200
        assert route.json()["intent"] == "password_reset"

        plan = client.post("/plan-next-step", json={"session_id": sid})
        assert plan.status_code == 200
        assert "account_id" in plan.json()["next_fields"]

        sub1 = client.post(
            "/submit-field",
            json={
                "session_id": sid,
                "field_name": "account_id",
                "value": "12345678",
            },
        )
        assert sub1.status_code == 200
        assert sub1.json()["accepted"] is True

        sub2 = client.post(
            "/submit-field",
            json={
                "session_id": sid,
                "field_name": "verification_code",
                "value": "654321",
            },
        )
        assert sub2.status_code == 200
        assert sub2.json()["accepted"] is True

        dispatch = client.post("/dispatch-action", json={"session_id": sid})
        assert dispatch.status_code == 200
        assert dispatch.json()["status"] == "completed"
        assert "Password reset initiated" in dispatch.json()["result"]

    def test_invalid_verification_code_rejected(self, monkeypatch):
        client = _client_for(monkeypatch, "password_reset")
        sid = "pw-http-2"

        client.post(
            "/route-intent", json={"session_id": sid, "utterance": "password reset"}
        )
        client.post(
            "/submit-field",
            json={
                "session_id": sid,
                "field_name": "account_id",
                "value": "12345678",
            },
        )

        bad = client.post(
            "/submit-field",
            json={
                "session_id": sid,
                "field_name": "verification_code",
                "value": "12",
            },
        )
        assert bad.status_code == 200
        assert bad.json()["accepted"] is False
        assert bad.json()["validation_error"] is not None


# ---------------------------------------------------------------------------
# Billing Dispute – full HTTP flow
# ---------------------------------------------------------------------------


class TestBillingDisputeHTTP:
    def test_full_flow(self, monkeypatch):
        client = _client_for(monkeypatch, "billing_dispute")
        sid = "bill-http-1"

        route = client.post(
            "/route-intent",
            json={"session_id": sid, "utterance": "I want to dispute a charge."},
        )
        assert route.status_code == 200
        assert route.json()["intent"] == "billing_dispute"

        fields = [
            ("account_number", "12345678"),
            ("charge_date", "03/01/2026"),
            ("charge_amount", "$95.00"),
            ("dispute_reason", "duplicate charge"),
        ]
        for name, value in fields:
            resp = client.post(
                "/submit-field",
                json={
                    "session_id": sid,
                    "field_name": name,
                    "value": value,
                },
            )
            assert resp.status_code == 200
            assert resp.json()["accepted"] is True, f"{name} rejected: {resp.json()}"

        dispatch = client.post("/dispatch-action", json={"session_id": sid})
        assert dispatch.status_code == 200
        assert dispatch.json()["status"] == "completed"
        assert "Dispute case opened" in dispatch.json()["result"]


# ---------------------------------------------------------------------------
# Order Status – full HTTP flow
# ---------------------------------------------------------------------------


class TestOrderStatusHTTP:
    def test_full_flow(self, monkeypatch):
        client = _client_for(monkeypatch, "order_status")
        sid = "ord-http-1"

        client.post(
            "/route-intent", json={"session_id": sid, "utterance": "Where is my order?"}
        )

        sub = client.post(
            "/submit-field",
            json={
                "session_id": sid,
                "field_name": "order_number",
                "value": "ORD-123456",
            },
        )
        assert sub.status_code == 200
        assert sub.json()["accepted"] is True

        dispatch = client.post("/dispatch-action", json={"session_id": sid})
        assert dispatch.status_code == 200
        assert dispatch.json()["status"] == "completed"
        assert "ORD-123456" in dispatch.json()["result"]


# ---------------------------------------------------------------------------
# Update Profile – full HTTP flow
# ---------------------------------------------------------------------------


class TestUpdateProfileHTTP:
    def test_full_flow(self, monkeypatch):
        client = _client_for(monkeypatch, "update_profile")
        sid = "prof-http-1"

        client.post(
            "/route-intent", json={"session_id": sid, "utterance": "Update my profile."}
        )

        for name, value in [
            ("account_number", "12345678"),
            ("field_to_update", "email"),
            ("new_value", "new@example.com"),
        ]:
            resp = client.post(
                "/submit-field",
                json={
                    "session_id": sid,
                    "field_name": name,
                    "value": value,
                },
            )
            assert resp.status_code == 200
            assert resp.json()["accepted"] is True, f"{name} rejected"

        dispatch = client.post("/dispatch-action", json={"session_id": sid})
        assert dispatch.status_code == 200
        assert dispatch.json()["status"] == "completed"
        assert "Profile updated" in dispatch.json()["result"]


# ---------------------------------------------------------------------------
# Cancel Service – full HTTP flow
# ---------------------------------------------------------------------------


class TestCancelServiceHTTP:
    def test_full_flow_confirmed(self, monkeypatch):
        client = _client_for(monkeypatch, "cancel_service")
        sid = "cancel-http-1"

        client.post(
            "/route-intent", json={"session_id": sid, "utterance": "Cancel my service."}
        )

        for name, value in [
            ("account_number", "12345678"),
            ("cancellation_reason", "moving"),
            ("confirm_cancel", "yes"),
        ]:
            resp = client.post(
                "/submit-field",
                json={
                    "session_id": sid,
                    "field_name": name,
                    "value": value,
                },
            )
            assert resp.status_code == 200
            assert resp.json()["accepted"] is True, f"{name} rejected"

        dispatch = client.post("/dispatch-action", json={"session_id": sid})
        assert dispatch.status_code == 200
        assert dispatch.json()["status"] == "completed"
        assert "Service cancelled" in dispatch.json()["result"]

    def test_cancel_denied(self, monkeypatch):
        client = _client_for(monkeypatch, "cancel_service")
        sid = "cancel-http-2"

        client.post(
            "/route-intent", json={"session_id": sid, "utterance": "Cancel my service."}
        )
        client.post(
            "/submit-field",
            json={
                "session_id": sid,
                "field_name": "account_number",
                "value": "12345678",
            },
        )
        client.post(
            "/submit-field",
            json={
                "session_id": sid,
                "field_name": "cancellation_reason",
                "value": "moving",
            },
        )
        client.post(
            "/submit-field",
            json={"session_id": sid, "field_name": "confirm_cancel", "value": "no"},
        )

        dispatch = client.post("/dispatch-action", json={"session_id": sid})
        assert dispatch.status_code == 200
        assert dispatch.json()["status"] == "completed"
        assert "remains active" in dispatch.json()["result"]


# ---------------------------------------------------------------------------
# Negative / edge-case paths
# ---------------------------------------------------------------------------


class TestNegativePaths:
    def test_plan_unknown_session_returns_404(self, monkeypatch):
        client = _client_for(monkeypatch, "password_reset")
        resp = client.post("/plan-next-step", json={"session_id": "nonexistent"})
        assert resp.status_code == 404

    def test_submit_field_unknown_session_returns_404(self, monkeypatch):
        client = _client_for(monkeypatch, "password_reset")
        resp = client.post(
            "/submit-field",
            json={
                "session_id": "nonexistent",
                "field_name": "account_id",
                "value": "123",
            },
        )
        assert resp.status_code == 404

    def test_dispatch_missing_fields_returns_blocked(self, monkeypatch):
        client = _client_for(monkeypatch, "password_reset")
        sid = "block-1"

        client.post(
            "/route-intent", json={"session_id": sid, "utterance": "password reset"}
        )
        dispatch = client.post("/dispatch-action", json={"session_id": sid})
        assert dispatch.status_code == 200
        assert dispatch.json()["status"] == "blocked"

    def test_escalation_summary_no_intent(self, monkeypatch):
        client = _client_for(monkeypatch, "password_reset")
        sid = "esc-no-intent"
        service = app_mod._SERVICE
        assert service is not None
        service.create_session(channel="text", session_id=sid)

        resp = client.post("/escalation-summary", json={"session_id": sid})
        assert resp.status_code == 200
        assert resp.json()["intent"] is None

    def test_submit_document_unknown_session_returns_404(self, monkeypatch):
        client = _client_for(monkeypatch, "password_reset")
        resp = client.post(
            "/submit-document",
            json={
                "session_id": "nonexistent",
                "document_text": "some text",
            },
        )
        assert resp.status_code == 404

    def test_concurrent_sessions_independent(self, monkeypatch):
        client = _client_for(monkeypatch, "password_reset")

        client.post("/route-intent", json={"session_id": "s1", "utterance": "reset"})
        client.post("/route-intent", json={"session_id": "s2", "utterance": "reset"})

        client.post(
            "/submit-field",
            json={
                "session_id": "s1",
                "field_name": "account_id",
                "value": "11111111",
            },
        )
        client.post(
            "/submit-field",
            json={
                "session_id": "s2",
                "field_name": "account_id",
                "value": "22222222",
            },
        )

        plan1 = client.post("/plan-next-step", json={"session_id": "s1"}).json()
        plan2 = client.post("/plan-next-step", json={"session_id": "s2"}).json()

        assert "verification_code" in plan1["next_fields"]
        assert "verification_code" in plan2["next_fields"]
        assert "account_id" not in plan1["missing_required_fields"]
        assert "account_id" not in plan2["missing_required_fields"]
