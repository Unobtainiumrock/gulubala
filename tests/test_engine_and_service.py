import pytest

from dialogue.manager import WorkflowEngine
from services.orchestrator import CallCenterService
from services.session_store import InMemorySessionStore
from workflows.registry import get_workflow

from tests.conftest import make_service, stub_field_extractor


def test_retry_limit_escalates_password_reset():
    engine = WorkflowEngine(field_extractor=stub_field_extractor, summary_builder=lambda payload: "summary")
    workflow = get_workflow("password_reset")
    session = InMemorySessionStore().create_session(channel="text")
    session.intent = "password_reset"

    accepted = engine.submit_field(session, workflow, "account_id", "12345678")
    assert accepted["accepted"] is True

    for _ in range(3):
        result = engine.submit_field(session, workflow, "verification_code", "12")

    assert result["accepted"] is False
    assert session.escalate is True
    assert session.escalation_reason == "validation_retry_limit"


def test_password_reset_happy_path(password_reset_service: CallCenterService):
    session = password_reset_service.create_session(channel="text")

    # Initial utterance - no fields extractable
    response = password_reset_service.handle_user_turn(session.session_id, "I can't log into my account.")
    assert not response["resolved"]

    # Two tokens: account_id gets first, verification_code gets second
    response = password_reset_service.handle_user_turn(session.session_id, "12345678 654321")
    assert response["resolved"] is True
    assert "Password reset initiated" in response["message"]


def test_password_reset_invalid_code_three_times_escalates(password_reset_service: CallCenterService):
    """Use submit_field to isolate the retry-escalation path from multi-field extraction."""
    session = password_reset_service.create_session(channel="text")

    password_reset_service.route_intent(session.session_id, "I can't log into my account.")
    password_reset_service.submit_field(session.session_id, "account_id", "12345678")

    # Three invalid verification codes (too short for 4-8 digit validator)
    password_reset_service.submit_field(session.session_id, "verification_code", "12")
    password_reset_service.submit_field(session.session_id, "verification_code", "34")
    result = password_reset_service.submit_field(session.session_id, "verification_code", "56")

    final_state = password_reset_service.get_session(session.session_id)
    assert result["accepted"] is False
    assert final_state.escalate is True
    assert final_state.escalation_reason == "validation_retry_limit"


def test_billing_dispute_happy_path(billing_service: CallCenterService):
    session = billing_service.create_session(channel="text")

    # Turn 1: intent classified, dispute_reason extracted from free text
    billing_service.handle_user_turn(session.session_id, "I need to dispute a charge on my bill.")

    # Turn 2: provide remaining 3 structured fields in one utterance
    response = billing_service.handle_user_turn(
        session.session_id, "12345678 03/01/2026 $95.00"
    )

    assert response["resolved"] is True
    assert "Dispute case opened" in response["message"]


def test_billing_document_mismatch_escalates(billing_service: CallCenterService):
    session = billing_service.create_session(channel="text")

    billing_service.route_intent(session.session_id, "I need to dispute a charge.")
    billing_service.submit_field(session.session_id, "account_number", "12345678")
    billing_service.submit_field(session.session_id, "charge_date", "2026-03-01")
    billing_service.submit_field(session.session_id, "charge_amount", "$95.00")
    billing_service.submit_field(session.session_id, "dispute_reason", "incorrect amount")

    result = billing_service.submit_supporting_document(
        session.session_id,
        "Merchant: ACME\ncharge date: 2026-03-02\namount: $95.00\nreference: REF-1234",
    )

    final_state = billing_service.get_session(session.session_id)
    assert result["mismatches"] == ["charge_date"]
    assert final_state.escalate is True
    assert final_state.escalation_reason == "document_mismatch"


def test_backend_failure_propagates_to_escalation(monkeypatch: pytest.MonkeyPatch):
    service = make_service(monkeypatch, "order_status")
    session = service.create_session(channel="text")
    service.route_intent(session.session_id, "Where is my order?")
    service.submit_field(session.session_id, "order_number", "ORD-123456")

    monkeypatch.setattr("services.orchestrator.execute_action", lambda action, fields: (_ for _ in ()).throw(RuntimeError("backend down")))
    result = service.dispatch_action(session.session_id)

    final_state = service.get_session(session.session_id)
    assert result["status"] == "failed"
    assert final_state.escalation_reason == "backend_failure"


@pytest.mark.parametrize(
    ("intent", "field_updates", "expected_fragment"),
    [
        (
            "order_status",
            [("order_number", "ORD-123456")],
            "Order ORD-123456",
        ),
        (
            "update_profile",
            [("account_number", "12345678"), ("field_to_update", "email"), ("new_value", "new@example.com")],
            "Profile updated",
        ),
        (
            "cancel_service",
            [("account_number", "12345678"), ("cancellation_reason", "moving"), ("confirm_cancel", "yes")],
            "Service cancelled",
        ),
    ],
)
def test_other_workflows_dispatch(monkeypatch: pytest.MonkeyPatch, intent: str, field_updates, expected_fragment: str):
    service = make_service(monkeypatch, intent)
    session = service.create_session(channel="text")
    service.route_intent(session.session_id, "start")
    for field_name, value in field_updates:
        response = service.submit_field(session.session_id, field_name, value)
        assert response["accepted"] is True

    result = service.dispatch_action(session.session_id)

    assert result["status"] == "completed"
    assert expected_fragment in result["result"]
