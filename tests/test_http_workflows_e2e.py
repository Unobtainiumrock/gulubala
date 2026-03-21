"""DEV-22: HTTP integration tests for all workflows (stepwise API).

Happy paths: POST /route-intent → /plan-next-step → /submit-field … → /dispatch-action.
Escalations: one distinct scenario per intent (see module docstrings on test classes).
"""

from __future__ import annotations

import pytest

import api.app as api_app
from api.app import FastAPI, create_app
from tests.conftest import make_service

if FastAPI is not None:
    from fastapi.testclient import TestClient


def _require_fastapi():
    if FastAPI is None:  # pragma: no cover
        pytest.skip("FastAPI not installed")


def _client(monkeypatch: pytest.MonkeyPatch, intent: str) -> "TestClient":
    service = make_service(monkeypatch, intent)
    api_app._SERVICE = service
    return TestClient(create_app())


def _route(client: "TestClient", session_id: str, utterance: str) -> dict:
    r = client.post("/route-intent", json={"session_id": session_id, "utterance": utterance})
    assert r.status_code == 200
    data = r.json()
    assert data.get("escalate") is False
    return data


def _plan(client: "TestClient", session_id: str) -> dict:
    r = client.post("/plan-next-step", json={"session_id": session_id})
    assert r.status_code == 200
    return r.json()


def _submit(client: "TestClient", session_id: str, field_name: str, value: str) -> dict:
    r = client.post(
        "/submit-field",
        json={"session_id": session_id, "field_name": field_name, "value": value},
    )
    assert r.status_code == 200
    return r.json()


def _dispatch(client: "TestClient", session_id: str) -> dict:
    r = client.post("/dispatch-action", json={"session_id": session_id})
    assert r.status_code == 200
    return r.json()


class TestHttpHappyPaths:
    """End-to-end success paths over the stepwise REST surface."""

    def test_password_reset(self, monkeypatch: pytest.MonkeyPatch):
        _require_fastapi()
        sid = "http-happy-pw"
        client = _client(monkeypatch, "password_reset")

        _route(client, sid, "I cannot log in.")
        plan = _plan(client, sid)
        assert "account_id" in plan["next_fields"]
        assert "verification_code" in plan["next_fields"]
        assert plan["escalate"] is False

        assert _submit(client, sid, "account_id", "12345678")["accepted"] is True
        plan2 = _plan(client, sid)
        assert "verification_code" in plan2["next_fields"]
        joined = " ".join(plan2["next_questions"]).lower()
        assert "verification" in joined and "6" in joined

        assert _submit(client, sid, "verification_code", "654321")["accepted"] is True

        out = _dispatch(client, sid)
        assert out["status"] == "completed"
        assert out["escalate"] is False
        assert "Password reset initiated" in (out["result"] or "")

    def test_billing_dispute(self, monkeypatch: pytest.MonkeyPatch):
        _require_fastapi()
        sid = "http-happy-bill"
        client = _client(monkeypatch, "billing_dispute")

        _route(client, sid, "I need to dispute a charge on my bill.")
        plan = _plan(client, sid)
        assert "account_number" in plan["next_fields"]
        assert plan["escalate"] is False

        assert _submit(client, sid, "account_number", "12345678")["accepted"] is True
        assert _submit(client, sid, "charge_date", "03/01/2026")["accepted"] is True
        p = _plan(client, sid)
        assert "charge_amount" in p["next_fields"] or p["missing_required_fields"]

        assert _submit(client, sid, "charge_amount", "$95.00")["accepted"] is True
        assert _submit(client, sid, "dispute_reason", "charged twice for same item")["accepted"] is True

        out = _dispatch(client, sid)
        assert out["status"] == "completed"
        assert "Dispute case opened" in (out["result"] or "")

    def test_order_status(self, monkeypatch: pytest.MonkeyPatch):
        _require_fastapi()
        sid = "http-happy-order"
        client = _client(monkeypatch, "order_status")

        _route(client, sid, "Where is my package?")
        plan = _plan(client, sid)
        assert "order_number" in plan["next_fields"]

        assert _submit(client, sid, "order_number", "ORD-123456")["accepted"] is True

        out = _dispatch(client, sid)
        assert out["status"] == "completed"
        assert "Order ORD-123456" in (out["result"] or "")

    def test_cancel_service(self, monkeypatch: pytest.MonkeyPatch):
        _require_fastapi()
        sid = "http-happy-cancel"
        client = _client(monkeypatch, "cancel_service")

        _route(client, sid, "I want to cancel my service.")
        plan = _plan(client, sid)
        assert "account_number" in plan["next_fields"]

        assert _submit(client, sid, "account_number", "12345678")["accepted"] is True
        assert _submit(client, sid, "cancellation_reason", "moving to a new city")["accepted"] is True
        assert _submit(client, sid, "confirm_cancel", "yes")["accepted"] is True

        out = _dispatch(client, sid)
        assert out["status"] == "completed"
        assert "Service cancelled" in (out["result"] or "")

    def test_update_profile(self, monkeypatch: pytest.MonkeyPatch):
        _require_fastapi()
        sid = "http-happy-profile"
        client = _client(monkeypatch, "update_profile")

        _route(client, sid, "I need to change my email on file.")
        plan = _plan(client, sid)
        assert "account_number" in plan["next_fields"]

        assert _submit(client, sid, "account_number", "12345678")["accepted"] is True
        assert _submit(client, sid, "field_to_update", "email")["accepted"] is True
        assert _submit(client, sid, "new_value", "new@example.com")["accepted"] is True

        out = _dispatch(client, sid)
        assert out["status"] == "completed"
        assert "Profile updated" in (out["result"] or "")


class TestHttpEscalations:
    """One escalation scenario per intent, using HTTP only (plus /submit-document where agreed)."""

    def test_password_reset_retry_limit(self, monkeypatch: pytest.MonkeyPatch):
        _require_fastapi()
        sid = "http-esc-pw-retry"
        client = _client(monkeypatch, "password_reset")

        _route(client, sid, "I cannot log in.")
        assert _submit(client, sid, "account_id", "12345678")["accepted"] is True

        last = None
        for _ in range(3):
            last = _submit(client, sid, "verification_code", "12")
        assert last is not None
        assert last["accepted"] is False
        assert last["escalate"] is True
        assert last["escalation_reason"] == "validation_retry_limit"

        plan = _plan(client, sid)
        assert plan["escalate"] is True
        assert plan["escalation_reason"] == "validation_retry_limit"

    def test_billing_document_mismatch(self, monkeypatch: pytest.MonkeyPatch):
        _require_fastapi()
        sid = "http-esc-bill-doc"
        client = _client(monkeypatch, "billing_dispute")

        _route(client, sid, "I need to dispute a charge.")
        _plan(client, sid)
        assert _submit(client, sid, "account_number", "12345678")["accepted"] is True
        assert _submit(client, sid, "charge_date", "2026-03-01")["accepted"] is True
        assert _submit(client, sid, "charge_amount", "$95.00")["accepted"] is True
        assert _submit(client, sid, "dispute_reason", "incorrect amount")["accepted"] is True

        doc = client.post(
            "/submit-document",
            json={
                "session_id": sid,
                "document_text": (
                    "Merchant: ACME\ncharge date: 2026-03-02\namount: $95.00\nreference: REF-1234"
                ),
            },
        )
        assert doc.status_code == 200
        body = doc.json()
        assert body["mismatches"] == ["charge_date"]

        plan = _plan(client, sid)
        assert plan["escalate"] is True
        assert plan["escalation_reason"] == "document_mismatch"

    def test_order_status_backend_failure(self, monkeypatch: pytest.MonkeyPatch):
        _require_fastapi()
        sid = "http-esc-order-be"
        client = _client(monkeypatch, "order_status")

        _route(client, sid, "Where is my order?")
        assert _submit(client, sid, "order_number", "ORD-123456")["accepted"] is True

        monkeypatch.setattr(
            "services.orchestrator.execute_action",
            lambda action, fields: (_ for _ in ()).throw(RuntimeError("backend down")),
        )
        out = _dispatch(client, sid)
        assert out["status"] == "failed"
        assert out["escalate"] is True
        assert out["escalation_reason"] == "backend_failure"
        assert "backend down" in (out["result"] or "")

    def test_cancel_service_backend_failure(self, monkeypatch: pytest.MonkeyPatch):
        _require_fastapi()
        sid = "http-esc-cancel-be"
        client = _client(monkeypatch, "cancel_service")

        _route(client, sid, "Cancel my subscription.")
        assert _submit(client, sid, "account_number", "12345678")["accepted"] is True
        assert _submit(client, sid, "cancellation_reason", "too expensive")["accepted"] is True
        assert _submit(client, sid, "confirm_cancel", "yes")["accepted"] is True

        monkeypatch.setattr(
            "services.orchestrator.execute_action",
            lambda action, fields: (_ for _ in ()).throw(RuntimeError("billing unavailable")),
        )
        out = _dispatch(client, sid)
        assert out["status"] == "failed"
        assert out["escalate"] is True
        assert out["escalation_reason"] == "backend_failure"

    def test_update_profile_backend_failure(self, monkeypatch: pytest.MonkeyPatch):
        _require_fastapi()
        sid = "http-esc-profile-be"
        client = _client(monkeypatch, "update_profile")

        _route(client, sid, "Update my profile.")
        assert _submit(client, sid, "account_number", "12345678")["accepted"] is True
        assert _submit(client, sid, "field_to_update", "phone")["accepted"] is True
        assert _submit(client, sid, "new_value", "5551234567")["accepted"] is True

        monkeypatch.setattr(
            "services.orchestrator.execute_action",
            lambda action, fields: (_ for _ in ()).throw(RuntimeError("crm timeout")),
        )
        out = _dispatch(client, sid)
        assert out["status"] == "failed"
        assert out["escalate"] is True
        assert out["escalation_reason"] == "backend_failure"
