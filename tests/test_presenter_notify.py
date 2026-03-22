"""Tests for Twilio presenter escalation / completion helpers."""

from __future__ import annotations

import config.models as config_models
import pytest

from telephony import presenter_notify


@pytest.fixture(autouse=True)
def _reset_twilio_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_models, "TWILIO_ACCOUNT_SID", "")
    monkeypatch.setattr(config_models, "TWILIO_AUTH_TOKEN", "")
    monkeypatch.setattr(config_models, "PRESENTER_PHONE_NUMBER", "")
    monkeypatch.setattr(config_models, "PUBLIC_API_BASE_URL", "")
    monkeypatch.setattr(config_models, "TWILIO_ESCALATION_BRIDGE", False)


def test_transcript_url_none_without_public_base() -> None:
    assert presenter_notify.transcript_url_for_session("abc") is None


def test_transcript_url_uses_public_base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_models, "PUBLIC_API_BASE_URL", "https://example.com/")
    url = presenter_notify.transcript_url_for_session("sess-1")
    assert url == "https://example.com/transcript/sess-1"


def test_notify_escalation_skips_without_twilio_config() -> None:
    assert (
        presenter_notify.notify_escalation(
            session_id="s1",
            reason="stuck",
            validated_fields={},
            twilio_call_sid="CAxxx",
        )
        is None
    )


def test_notify_completion_skips_without_twilio_config() -> None:
    presenter_notify.notify_completion(
        session_id="s1",
        summary="done",
        validated_fields={},
    )


def test_notify_escalation_invokes_twilio(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_models, "TWILIO_ACCOUNT_SID", "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    monkeypatch.setattr(config_models, "TWILIO_AUTH_TOKEN", "token")
    monkeypatch.setattr(config_models, "PRESENTER_PHONE_NUMBER", "+15551234567")

    sms_log: list[str] = []
    call_log: list[str] = []

    monkeypatch.setattr(
        presenter_notify,
        "send_sms",
        lambda body, **_: sms_log.append(body) or "SMxxx",
    )
    monkeypatch.setattr(
        presenter_notify,
        "call_presenter",
        lambda message, **_: call_log.append(message) or "CAyyy",
    )
    monkeypatch.setattr(
        presenter_notify,
        "bridge_to_conference",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("bridge should not run")),
    )

    result = presenter_notify.notify_escalation(
        session_id="session-99",
        reason="Need verification code",
        validated_fields={"account_number": "1234"},
        twilio_call_sid=None,
    )
    assert result is None
    assert len(sms_log) == 1 and "session-99" in sms_log[0]
    assert len(call_log) == 1 and "verification code" in call_log[0].lower()


def test_notify_escalation_bridge_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_models, "TWILIO_ACCOUNT_SID", "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    monkeypatch.setattr(config_models, "TWILIO_AUTH_TOKEN", "token")
    monkeypatch.setattr(config_models, "PRESENTER_PHONE_NUMBER", "+15551234567")
    monkeypatch.setattr(config_models, "TWILIO_ESCALATION_BRIDGE", True)

    monkeypatch.setattr(presenter_notify, "send_sms", lambda *a, **k: "SM1")
    monkeypatch.setattr(presenter_notify, "call_presenter", lambda *a, **k: "CA1")
    monkeypatch.setattr(
        presenter_notify,
        "bridge_to_conference",
        lambda conf, sid, _presenter, **k: {
            "conference_name": conf,
            "presenter_call_sid": "CAbridge",
        },
    )

    bridge = presenter_notify.notify_escalation(
        session_id="abc-def",
        reason="help",
        validated_fields={},
        twilio_call_sid="CAivr",
    )
    assert bridge is not None
    assert bridge.presenter_call_sid == "CAbridge"
    assert bridge.conference_name.startswith("ivr_esc_")
