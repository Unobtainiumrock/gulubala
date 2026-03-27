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

    assert "account number" in response["message"]


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

    route = client.post(
        "/route-intent",
        json={"session_id": "api-session", "utterance": "I cannot log in."},
    )
    assert route.status_code == 200
    assert route.json()["intent"] == "password_reset"

    plan = client.post("/plan-next-step", json={"session_id": "api-session"})
    assert plan.status_code == 200
    assert "account_id" in plan.json()["next_fields"]

    submit_account = client.post(
        "/submit-field",
        json={
            "session_id": "api-session",
            "field_name": "account_id",
            "value": "12345678",
        },
    )
    assert submit_account.status_code == 200
    assert submit_account.json()["accepted"] is True

    submit_code = client.post(
        "/submit-field",
        json={
            "session_id": "api-session",
            "field_name": "verification_code",
            "value": "123456",
        },
    )
    assert submit_code.status_code == 200
    assert submit_code.json()["accepted"] is True

    dispatch = client.post("/dispatch-action", json={"session_id": "api-session"})
    assert dispatch.status_code == 200
    assert dispatch.json()["status"] == "completed"


def test_demo_routes_expose_scenarios_without_landing_page(
    monkeypatch: pytest.MonkeyPatch,
):
    if FastAPI is None:  # pragma: no cover
        pytest.skip("FastAPI not installed")

    from fastapi.testclient import TestClient

    service = make_service(monkeypatch, "password_reset")
    api_app._SERVICE = service
    client = TestClient(create_app())

    root = client.get("/")
    assert root.status_code == 404

    scenarios = client.get("/demo/scenarios")
    assert scenarios.status_code == 200
    scenario_ids = {item["id"] for item in scenarios.json()}
    assert {"password_reset", "cancel_service"} <= scenario_ids


def test_demo_guided_flow(monkeypatch: pytest.MonkeyPatch):
    if FastAPI is None:  # pragma: no cover
        pytest.skip("FastAPI not installed")

    from fastapi.testclient import TestClient

    service = make_service(monkeypatch, "password_reset")
    api_app._SERVICE = service
    client = TestClient(create_app())

    start = client.post(
        "/demo/start", json={"scenario_id": "password_reset", "channel": "voice"}
    )
    assert start.status_code == 200
    payload = start.json()
    assert payload["scenario"]["intent"] == "password_reset"
    assert "Callit-Dev" in payload["message"]
    assert payload["voice_response"]["voice_provider"]["type"] == "assistant_output"

    session_id = payload["session_id"]
    turn_one = client.post(
        "/demo/turn", json={"session_id": session_id, "utterance": "12345678"}
    )
    assert turn_one.status_code == 200
    assert "verification code" in turn_one.json()["message"]
    assert (
        turn_one.json()["voice_response"]["voice_provider"]["session_id"] == session_id
    )

    turn_two = client.post(
        "/demo/turn", json={"session_id": session_id, "utterance": "123456"}
    )
    assert turn_two.status_code == 200
    assert turn_two.json()["resolved"] is True


def test_demo_voice_turn(monkeypatch: pytest.MonkeyPatch):
    if FastAPI is None:  # pragma: no cover
        pytest.skip("FastAPI not installed")

    from base64 import b64encode
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        "services.orchestrator.transcribe_bytes", lambda **kwargs: "12345678"
    )

    service = make_service(monkeypatch, "password_reset")
    api_app._SERVICE = service
    client = TestClient(create_app())

    start = client.post(
        "/demo/start", json={"scenario_id": "password_reset", "channel": "voice"}
    )
    session_id = start.json()["session_id"]

    voice_turn = client.post(
        "/demo/voice-turn",
        json={
            "session_id": session_id,
            "audio_base64": b64encode(b"demo-bytes").decode("ascii"),
            "filename": "demo.webm",
            "content_type": "audio/webm",
        },
    )
    assert voice_turn.status_code == 200
    assert voice_turn.json()["transcript"] == "12345678"
    assert (
        voice_turn.json()["voice_response"]["voice_provider"]["session_id"]
        == session_id
    )


def test_document_adapter_extracts_supported_fields():
    workflow = get_workflow("billing_dispute")
    service = make_service(pytest.MonkeyPatch(), "billing_dispute")
    result = service.document_adapter.extract_fields(
        workflow,
        "Merchant: ACME\ncharge date: 2026-03-01\namount: $95.00\nreference: REF-1234",
    )

    assert result.fields["charge_date"] == "2026-03-01"
    assert result.fields["charge_amount"] == "$95.00"
