"""DEV-23: Verify structured logging covers FR10 requirements.

FR10 mandates logging: intent, fields collected, validation failures,
escalation triggers, and final disposition.
"""

from __future__ import annotations

import json
import logging

import pytest

from tests.conftest import make_service

LOGGER_NAME = "call_center"


def _parse_log_events(caplog):
    """Return all structured log payloads from captured records."""
    return [json.loads(r.message) for r in caplog.records if r.name == LOGGER_NAME]


def _events_by_type(caplog, event_type: str):
    return [e for e in _parse_log_events(caplog) if e["event"] == event_type]


# ---------------------------------------------------------------------------
# Gap 1: Multi-field capture must emit per-field field_submitted logs
# ---------------------------------------------------------------------------


class TestMultiFieldCaptureLogging:
    def test_multi_field_emits_per_field_logs(self, monkeypatch, caplog):
        svc = make_service(monkeypatch, "password_reset")
        s = svc.create_session(channel="text")
        svc.handle_user_turn(s.session_id, "I need to reset my password")
        caplog.clear()

        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            svc.handle_user_turn(s.session_id, "12345678 654321")

        field_logs = _events_by_type(caplog, "field_submitted")
        field_names = {l["data"]["submission"]["field_name"] for l in field_logs}
        assert "account_id" in field_names
        assert "verification_code" in field_names
        assert len(field_logs) >= 2


# ---------------------------------------------------------------------------
# Gap 2: DTMF path must emit conversation_turn
# ---------------------------------------------------------------------------


class TestDtmfConversationTurnLogging:
    def test_dtmf_emits_conversation_turn(self, monkeypatch, caplog):
        svc = make_service(monkeypatch, "password_reset")
        svc.create_session(channel="voice", session_id="dtmf-1")
        svc.route_intent("dtmf-1", "I need to reset my password")
        caplog.clear()

        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            result = svc.handle_voice_event({
                "type": "dtmf",
                "session_id": "dtmf-1",
                "digits": "12345678",
            })

        turn_logs = _events_by_type(caplog, "conversation_turn")
        assert len(turn_logs) >= 1
        assert turn_logs[0]["data"]["message"] == result["message"]


# ---------------------------------------------------------------------------
# FR10 spot-checks: intent, validation failures, escalation, disposition
# ---------------------------------------------------------------------------


class TestFR10FieldsPresent:
    def test_intent_logged_on_routing(self, monkeypatch, caplog):
        svc = make_service(monkeypatch, "password_reset")
        s = svc.create_session(channel="text")
        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            svc.handle_user_turn(s.session_id, "reset my password")

        intent_events = _events_by_type(caplog, "intent_routed")
        assert len(intent_events) >= 1
        assert intent_events[0]["intent"] == "password_reset"

    def test_validation_error_in_field_submitted(self, monkeypatch, caplog):
        svc = make_service(monkeypatch, "password_reset")
        s = svc.create_session(channel="text")
        svc.handle_user_turn(s.session_id, "reset my password")
        caplog.clear()

        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            svc.submit_field(s.session_id, "account_id", "bad")

        field_events = _events_by_type(caplog, "field_submitted")
        assert len(field_events) >= 1
        submission = field_events[0]["data"]["submission"]
        assert submission["accepted"] is False
        assert submission["validation_error"] is not None

    def test_escalation_reason_logged(self, monkeypatch, caplog):
        svc = make_service(monkeypatch, "password_reset")
        s = svc.create_session(channel="text")
        svc.handle_user_turn(s.session_id, "reset my password")
        caplog.clear()

        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            svc.handle_user_turn(s.session_id, "I want to speak to a human")

        events = _parse_log_events(caplog)
        escalated = [e for e in events if e.get("escalate") is True]
        assert len(escalated) >= 1
        assert escalated[0]["escalation_reason"] is not None

    def test_disposition_logged_on_completion(self, monkeypatch, caplog):
        svc = make_service(monkeypatch, "password_reset")
        s = svc.create_session(channel="text")
        svc.handle_user_turn(s.session_id, "reset my password")
        caplog.clear()

        with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
            svc.handle_user_turn(s.session_id, "12345678 654321")

        dispatch_events = _events_by_type(caplog, "action_dispatched")
        assert len(dispatch_events) >= 1
        assert dispatch_events[0]["data"]["result"]["status"] == "completed"
