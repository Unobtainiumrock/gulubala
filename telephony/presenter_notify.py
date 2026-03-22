"""Presenter / SMS hooks for IVR navigator completion and escalation."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

import config.models as config_models

logger = logging.getLogger(__name__)


@dataclass
class BridgeResult:
    """Returned when escalation moves the IVR leg into a Twilio conference."""

    conference_name: str
    presenter_call_sid: str


def transcript_url_for_session(session_id: str) -> str | None:
    """Public HTTPS link to the session transcript (for SMS / handoff)."""
    base = config_models.PUBLIC_API_BASE_URL.strip().rstrip("/")
    if not base:
        return None
    return f"{base}/transcript/{session_id}"


def send_sms(body: str, *, to: str | None = None) -> str:
    """Send SMS via Twilio; return message SID."""
    dest = (to or config_models.PRESENTER_PHONE_NUMBER or "").strip()
    if not all(
        [
            config_models.TWILIO_ACCOUNT_SID,
            config_models.TWILIO_AUTH_TOKEN,
            dest,
            config_models.TWILIO_AGENT_NUMBER,
        ]
    ):
        raise RuntimeError("Twilio SMS requires account, token, from, and destination numbers.")
    from twilio.rest import Client

    client = Client(config_models.TWILIO_ACCOUNT_SID, config_models.TWILIO_AUTH_TOKEN)
    msg = client.messages.create(
        to=dest,
        from_=config_models.TWILIO_AGENT_NUMBER,
        body=body,
    )
    return msg.sid


def call_presenter(message: str, **_: Any) -> str:
    """Place an outbound call to the presenter with a spoken summary (TwiML URL or inline)."""
    if not all(
        [
            config_models.TWILIO_ACCOUNT_SID,
            config_models.TWILIO_AUTH_TOKEN,
            config_models.PRESENTER_PHONE_NUMBER,
            config_models.TWILIO_AGENT_NUMBER,
        ]
    ):
        raise RuntimeError("Twilio voice requires account, token, from, and presenter numbers.")
    from twilio.rest import Client
    from xml.sax.saxutils import escape

    client = Client(config_models.TWILIO_ACCOUNT_SID, config_models.TWILIO_AUTH_TOKEN)
    safe = escape(message)
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response><Say voice=\"Polly.Joanna\">"
        f"{safe}"
        "</Say></Response>"
    )
    call = client.calls.create(
        to=config_models.PRESENTER_PHONE_NUMBER,
        from_=config_models.TWILIO_AGENT_NUMBER,
        twiml=twiml,
    )
    return call.sid


def bridge_to_conference(
    conference_name: str,
    ivr_call_sid: str,
    presenter_phone: str,
    **kwargs: Any,
) -> dict[str, str] | None:
    """Move the active IVR call and presenter into a Twilio conference.

    Override or extend for production; default implementation does not dial.
    """
    logger.warning(
        "bridge_to_conference not implemented (conf=%s ivr=%s presenter=%s)",
        conference_name,
        ivr_call_sid,
        presenter_phone,
    )
    return None


def notify_completion(
    session_id: str,
    summary: str | None,
    validated_fields: dict[str, str],
) -> None:
    """Best-effort notification when the navigator finishes successfully."""
    if not all(
        [
            config_models.TWILIO_ACCOUNT_SID,
            config_models.TWILIO_AUTH_TOKEN,
            config_models.PRESENTER_PHONE_NUMBER,
        ]
    ):
        return
    url = transcript_url_for_session(session_id)
    parts = [f"Session {session_id} completed."]
    if summary:
        parts.append(summary)
    if url:
        parts.append(f"Transcript: {url}")
    try:
        send_sms(" ".join(parts))
    except Exception as exc:
        logger.warning("notify_completion SMS failed: %s", exc)


def notify_escalation(
    *,
    session_id: str,
    reason: str,
    validated_fields: dict[str, str],
    twilio_call_sid: str | None,
) -> BridgeResult | None:
    """Escalation: optional SMS + presenter call; optional conference bridge."""
    url = transcript_url_for_session(session_id)
    logger.warning(
        "Escalation session=%s reason=%s call_sid=%s transcript=%s",
        session_id,
        reason,
        twilio_call_sid,
        url or "(no public base URL)",
    )

    if config_models.TWILIO_ESCALATION_BRIDGE and twilio_call_sid:
        conf = f"ivr_esc_{uuid.uuid4().hex[:12]}"
        presenter = (config_models.PRESENTER_PHONE_NUMBER or "").strip()
        raw = bridge_to_conference(conf, twilio_call_sid, presenter)
        if raw is None:
            return None
        return BridgeResult(
            conference_name=raw["conference_name"],
            presenter_call_sid=raw["presenter_call_sid"],
        )

    if all(
        [
            config_models.TWILIO_ACCOUNT_SID,
            config_models.TWILIO_AUTH_TOKEN,
            config_models.PRESENTER_PHONE_NUMBER,
        ]
    ):
        parts = [f"Escalation {session_id}: {reason}."]
        if validated_fields:
            parts.append(f"Fields: {validated_fields}")
        if url:
            parts.append(f"Transcript: {url}")
        sms_body = " ".join(parts)
        send_sms(sms_body)
        call_presenter(
            message=f"Escalation for session {session_id}. {reason}.",
        )

    return None
