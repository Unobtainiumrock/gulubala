"""Tests for deterministic demo presenter / escalation overrides."""

from __future__ import annotations

from contracts.prompts import IvrActionResponse
from calltree.demo_human_flows import apply_demo_human_flow_overrides


def _wait() -> IvrActionResponse:
    return IvrActionResponse(action="wait", reasoning="llm")


def test_disabled_returns_llm_action():
    action = apply_demo_human_flow_overrides(
        enabled=False,
        transcript_text="What is the main reason you would like to cancel today?",
        classification_category="info_request",
        available_fields={"account_number": "1"},
        escalated=False,
        action=_wait(),
    )
    assert action.action == "wait"


def test_cancel_reason_triggers_request_info():
    action = apply_demo_human_flow_overrides(
        enabled=True,
        transcript_text="Thank you. What is the main reason you would like to cancel today?",
        classification_category="info_request",
        available_fields={"account_number": "12345678", "confirm_cancel": "yes"},
        escalated=False,
        action=_wait(),
    )
    assert action.action == "request_info"
    assert action.requested_field == "cancellation_reason"
    assert action.field_prompt


def test_speak_reason_when_already_known():
    action = apply_demo_human_flow_overrides(
        enabled=True,
        transcript_text="What is the main reason you would like to cancel today?",
        classification_category="info_request",
        available_fields={"cancellation_reason": "too expensive"},
        escalated=False,
        action=_wait(),
    )
    assert action.action == "speak"
    assert action.speech_text == "too expensive"


def test_retention_line_triggers_escalate():
    action = apply_demo_human_flow_overrides(
        enabled=True,
        transcript_text="Hi, this is Alex from Acme retention. What can I do to keep you?",
        classification_category="menu",
        available_fields={"account_number": "1"},
        escalated=False,
        action=_wait(),
    )
    assert action.action == "escalate"
    assert action.escalation_reason


def test_human_agent_category_triggers_escalate():
    action = apply_demo_human_flow_overrides(
        enabled=True,
        transcript_text="Hello there",
        classification_category="human_agent",
        available_fields={},
        escalated=False,
        action=_wait(),
    )
    assert action.action == "escalate"


def test_root_menu_sends_dtmf_1():
    action = apply_demo_human_flow_overrides(
        enabled=True,
        transcript_text="Press 1 for billing, 2 for account services, or 3 for order support.",
        classification_category="menu",
        available_fields={},
        escalated=False,
        action=_wait(),
    )
    assert action.action == "send_dtmf"
    assert action.dtmf_digits == "1"


def test_cancel_submenu_sends_dtmf_2():
    action = apply_demo_human_flow_overrides(
        enabled=True,
        transcript_text="For a billing dispute, press 1. To cancel your service, press 2.",
        classification_category="menu",
        available_fields={},
        escalated=False,
        action=_wait(),
    )
    assert action.action == "send_dtmf"
    assert action.dtmf_digits == "2"


def test_hold_line_waits():
    action = apply_demo_human_flow_overrides(
        enabled=True,
        transcript_text="Please hold while I connect you to our cancellation specialist.",
        classification_category="info_request",
        available_fields={},
        escalated=False,
        action=_wait(),
    )
    assert action.action == "wait"


def test_account_number_sends_dtmf():
    action = apply_demo_human_flow_overrides(
        enabled=True,
        transcript_text="Please say or enter your account number so I can locate the subscription.",
        classification_category="info_request",
        available_fields={"account_number": "12345678"},
        escalated=False,
        action=_wait(),
    )
    assert action.action == "send_dtmf"
    assert action.dtmf_digits == "12345678"


def test_confirm_cancel_speaks_yes():
    action = apply_demo_human_flow_overrides(
        enabled=True,
        transcript_text="To confirm, would you like me to cancel the subscription now? Please say yes or no.",
        classification_category="info_request",
        available_fields={"confirm_cancel": "yes"},
        escalated=False,
        action=_wait(),
    )
    assert action.action == "speak"
    assert action.speech_text == "yes"


def test_no_override_when_already_escalated():
    action = apply_demo_human_flow_overrides(
        enabled=True,
        transcript_text="Hi, this is Alex from Acme retention.",
        classification_category="human_agent",
        available_fields={},
        escalated=True,
        action=_wait(),
    )
    assert action.action == "wait"
