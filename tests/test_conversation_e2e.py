"""End-to-end conversational flow tests for all 5 workflows.

Each test exercises the full dialogue loop via ``handle_user_turn`` with
stubbed LLM services.  This validates the orchestrator's conversational
behaviour (intent routing, multi-field extraction, action dispatch,
escalation) across every supported workflow.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.orchestrator import CallCenterService
from tests.conftest import make_service


# ---------------------------------------------------------------------------
# Password Reset
# ---------------------------------------------------------------------------

class TestPasswordResetConversation:
    def test_happy_path_two_turns(self, monkeypatch):
        svc = make_service(monkeypatch, "password_reset")
        s = svc.create_session(channel="text")

        r1 = svc.handle_user_turn(s.session_id, "I need to reset my password")
        assert not r1["resolved"]
        assert not r1["escalated"]

        r2 = svc.handle_user_turn(s.session_id, "12345678 654321")
        assert r2["resolved"] is True
        assert "Password reset initiated" in r2["message"]

    def test_stall_detection_escalates(self, monkeypatch):
        """After 8+ turns with no progress the session should escalate."""
        svc = make_service(monkeypatch, "password_reset")
        s = svc.create_session(channel="text")

        svc.handle_user_turn(s.session_id, "I need to reset my password")

        for _ in range(8):
            resp = svc.handle_user_turn(s.session_id, "um I don't know")

        final = svc.get_session(s.session_id)
        assert final.escalate is True
        assert final.escalation_reason == "conversation_stalled"

    def test_human_request_mid_flow(self, monkeypatch):
        svc = make_service(monkeypatch, "password_reset")
        s = svc.create_session(channel="text")

        svc.handle_user_turn(s.session_id, "I need to reset my password")
        r = svc.handle_user_turn(s.session_id, "let me speak to a human")
        assert r["escalated"] is True


# ---------------------------------------------------------------------------
# Billing Dispute
# ---------------------------------------------------------------------------

class TestBillingDisputeConversation:
    def test_happy_path(self, monkeypatch):
        svc = make_service(monkeypatch, "billing_dispute")
        s = svc.create_session(channel="text")

        svc.handle_user_turn(s.session_id, "I need to dispute a charge on my bill.")
        r2 = svc.handle_user_turn(s.session_id, "12345678 03/01/2026 $95.00")
        assert r2["resolved"] is True
        assert "Dispute case opened" in r2["message"]

    def test_partial_then_complete(self, monkeypatch):
        """Provide fields across multiple turns."""
        svc = make_service(monkeypatch, "billing_dispute")
        s = svc.create_session(channel="text")

        svc.handle_user_turn(s.session_id, "I want to dispute a charge.")

        r2 = svc.handle_user_turn(s.session_id, "12345678")
        assert not r2["resolved"]

        r3 = svc.handle_user_turn(s.session_id, "03/01/2026 $95.00")
        assert r3["resolved"] is True


# ---------------------------------------------------------------------------
# Order Status
# ---------------------------------------------------------------------------

class TestOrderStatusConversation:
    def test_happy_path(self, monkeypatch):
        svc = make_service(monkeypatch, "order_status")
        s = svc.create_session(channel="text")

        r1 = svc.handle_user_turn(s.session_id, "Where is my order?")
        assert not r1["resolved"]

        r2 = svc.handle_user_turn(s.session_id, "ORD-123456")
        assert r2["resolved"] is True
        assert "ORD-123456" in r2["message"]

    def test_invalid_order_number_re_asks(self, monkeypatch):
        svc = make_service(monkeypatch, "order_status")
        s = svc.create_session(channel="text")

        svc.handle_user_turn(s.session_id, "Where is my order?")
        r2 = svc.handle_user_turn(s.session_id, "ab")
        assert not r2["resolved"]
        assert "order" in r2["message"].lower()


# ---------------------------------------------------------------------------
# Update Profile
# ---------------------------------------------------------------------------

class TestUpdateProfileConversation:
    def test_happy_path(self, monkeypatch):
        svc = make_service(monkeypatch, "update_profile")
        s = svc.create_session(channel="text")

        r1 = svc.handle_user_turn(s.session_id, "I need to update my profile")
        assert not r1["resolved"]

        r2 = svc.handle_user_turn(s.session_id, "12345678 email new@example.com")
        assert r2["resolved"] is True
        assert "Profile updated" in r2["message"]


# ---------------------------------------------------------------------------
# Cancel Service
# ---------------------------------------------------------------------------

class TestCancelServiceConversation:
    def test_confirmed_cancellation(self, monkeypatch):
        """The stub extractor greedily assigns tokens to confirm_cancel,
        so we feed fields across separate turns to avoid mis-assignment."""
        svc = make_service(monkeypatch, "cancel_service")
        s = svc.create_session(channel="text")

        r1 = svc.handle_user_turn(s.session_id, "I want to cancel my service")
        assert not r1["resolved"]

        r2 = svc.handle_user_turn(s.session_id, "12345678")
        assert not r2["resolved"]

        r3 = svc.handle_user_turn(s.session_id, "yes")
        assert r3["resolved"] is True
        assert "Service cancelled" in r3["message"]

    def test_denied_cancellation(self, monkeypatch):
        svc = make_service(monkeypatch, "cancel_service")
        s = svc.create_session(channel="text")

        svc.handle_user_turn(s.session_id, "I want to cancel my service")
        svc.handle_user_turn(s.session_id, "12345678")
        r3 = svc.handle_user_turn(s.session_id, "no")
        assert r3["resolved"] is True
        assert "remains active" in r3["message"]


# ---------------------------------------------------------------------------
# Cross-cutting: escalation summary after dispatch failure
# ---------------------------------------------------------------------------

class TestEscalationSummaryFlow:
    def test_backend_failure_produces_summary(self, monkeypatch):
        svc = make_service(monkeypatch, "order_status")
        s = svc.create_session(channel="text")

        svc.route_intent(s.session_id, "Where is my order?")
        svc.submit_field(s.session_id, "order_number", "ORD-123456")

        monkeypatch.setattr(
            "services.orchestrator.execute_action",
            lambda action, fields: (_ for _ in ()).throw(RuntimeError("backend down")),
        )
        svc.dispatch_action(s.session_id)

        summary = svc.build_escalation_summary(s.session_id)
        assert summary["escalation_reason"] == "backend_failure"
        assert isinstance(summary["summary"], str)
        assert len(summary["summary"]) > 0
