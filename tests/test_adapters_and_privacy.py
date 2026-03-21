import pytest

import api.app as api_app
from api.app import FastAPI, app, create_app
from services.logging import redact_mapping, serialize_state_for_logs
from workflows.registry import get_workflow

from tests.conftest import make_service


def test_caller_request_human_escalates(monkeypatch: pytest.MonkeyPatch):
    service = make_service(monkeypatch, "password_reset")
    session = service.create_session(channel="text")

    service.handle_user_turn(session.session_id, "I cannot log in.")
    response = service.handle_user_turn(session.session_id, "I want a real person.")

    final_state = service.get_session(session.session_id)
    assert response["escalated"] is True
    assert final_state.escalation_reason == "user_request_human"


def test_asr_confusion_reasks_same_field(monkeypatch: pytest.MonkeyPatch):
    service = make_service(monkeypatch, "password_reset")
    session = service.create_session(channel="text")

    service.handle_user_turn(session.session_id, "I cannot log in.")
    response = service.handle_user_turn(session.session_id, "static noise only")

    assert "account ID" in response["message"]


def test_dtmf_event_submits_numeric_field(monkeypatch: pytest.MonkeyPatch):
    service = make_service(monkeypatch, "password_reset")
    session = service.create_session(channel="voice")
    service.route_intent(session.session_id, "I cannot log in.")

    response = service.handle_voice_event({"type": "dtmf", "session_id": session.session_id, "digits": "12345678"})

    assert "verification code" in response["message"]
    final_state = service.get_session(session.session_id)
    assert final_state.validated_fields["account_id"] == "12345678"


def test_boson_interrupt_preserves_state(monkeypatch: pytest.MonkeyPatch):
    service = make_service(monkeypatch, "password_reset")
    session = service.create_session(channel="voice")
    service.route_intent(session.session_id, "I cannot log in.")
    service.submit_field(session.session_id, "account_id", "12345678")

    response = service.handle_voice_event({"type": "interrupt", "session_id": session.session_id, "reason": "barge-in"})

    final_state = service.get_session(session.session_id)
    assert response["message"] == "Interruption registered."
    assert final_state.validated_fields["account_id"] == "12345678"
    assert final_state.metadata["boson_interrupted"] is True


def test_redaction_helpers_mask_sensitive_fields():
    redacted = redact_mapping(
        {
            "account_number": "12345678",
            "email": "user@example.com",
            "dispute_reason": "incorrect amount",
        }
    )

    assert redacted["account_number"] != "12345678"
    assert redacted["email"] != "user@example.com"
    assert redacted["dispute_reason"] == "incorrect amount"


def test_log_state_serialization_uses_redaction(monkeypatch: pytest.MonkeyPatch):
    service = make_service(monkeypatch, "password_reset")
    session = service.create_session(channel="text")
    service.route_intent(session.session_id, "I cannot log in.")
    service.submit_field(session.session_id, "account_id", "12345678")

    payload = serialize_state_for_logs(service.get_session(session.session_id))

    assert payload["validated_fields"]["account_id"] != "12345678"


def test_api_module_handles_missing_fastapi_dependency():
    if FastAPI is None:
        with pytest.raises(ModuleNotFoundError):
            create_app()
        assert app is None
    else:  # pragma: no cover
        assert app is not None


def test_api_smoke_flow(monkeypatch: pytest.MonkeyPatch):
    if FastAPI is None:  # pragma: no cover
        pytest.skip("FastAPI not installed")

    from fastapi.testclient import TestClient

    service = make_service(monkeypatch, "password_reset")
    api_app._SERVICE = service
    client = TestClient(create_app())

    route = client.post("/route-intent", json={"session_id": "api-session", "utterance": "I cannot log in."})
    assert route.status_code == 200
    assert route.json()["intent"] == "password_reset"

    plan = client.post("/plan-next-step", json={"session_id": "api-session"})
    assert plan.status_code == 200
    assert plan.json()["next_field"] == "account_id"

    submit_account = client.post(
        "/submit-field",
        json={"session_id": "api-session", "field_name": "account_id", "value": "12345678"},
    )
    assert submit_account.status_code == 200
    assert submit_account.json()["accepted"] is True

    submit_code = client.post(
        "/submit-field",
        json={"session_id": "api-session", "field_name": "verification_code", "value": "123456"},
    )
    assert submit_code.status_code == 200
    assert submit_code.json()["accepted"] is True

    dispatch = client.post("/dispatch-action", json={"session_id": "api-session"})
    assert dispatch.status_code == 200
    assert dispatch.json()["status"] == "completed"


def test_document_adapter_extracts_supported_fields():
    workflow = get_workflow("billing_dispute")
    service = make_service(pytest.MonkeyPatch(), "billing_dispute")
    result = service.document_adapter.extract_fields(
        workflow,
        "Merchant: ACME\ncharge date: 2026-03-01\namount: $95.00\nreference: REF-1234",
    )

    assert result.fields["charge_date"] == "2026-03-01"
    assert result.fields["charge_amount"] == "$95.00"
