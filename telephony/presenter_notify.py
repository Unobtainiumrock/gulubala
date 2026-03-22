"""Presenter / SMS hooks for IVR navigator completion and escalation."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

import config.models as config_models

logger = logging.getLogger(__name__)


def _require_twilio_voice() -> None:
    if not all(
        [
            config_models.TWILIO_ACCOUNT_SID,
            config_models.TWILIO_AUTH_TOKEN,
            config_models.PRESENTER_PHONE_NUMBER,
            config_models.TWILIO_AGENT_NUMBER,
        ]
    ):
        raise RuntimeError("Twilio voice requires account, token, from, and presenter numbers.")


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
    _require_twilio_voice()
    from twilio.rest import Client
    from xml.sax.saxutils import escape

    client = Client(config_models.TWILIO_ACCOUNT_SID, config_models.TWILIO_AUTH_TOKEN)
    safe = escape(message)
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response><Say voice="Polly.Joanna">'
        f"{safe}"
        "</Say></Response>"
    )
    call = client.calls.create(
        to=config_models.PRESENTER_PHONE_NUMBER,
        from_=config_models.TWILIO_AGENT_NUMBER,
        twiml=twiml,
    )
    return call.sid


_INTENT_LABELS: dict[str, str] = {
    "cancel_service": "cancel a subscription",
    "password_reset": "reset a password",
    "billing_dispute": "handle a billing dispute",
    "update_profile": "update an account profile",
    "order_status": "check an order status",
}


def _build_presenter_intro(field_name: str, intent: str | None = None) -> str:
    """Build a brief, conversational intro for the presenter side-call."""
    friendly_name = field_name.replace("_", " ")
    purpose = _INTENT_LABELS.get(intent or "", "complete a task")
    return (
        f"Hey, the agent is mid-call trying to {purpose} "
        f"and needs a {friendly_name} from you."
    )


def call_presenter_for_info(
    *,
    session_id: str,
    field_name: str,
    field_prompt: str,
    callback_base_url: str,
    intent: str | None = None,
) -> str:
    """Call the presenter and use ``<Gather input="speech">`` to collect a field value.

    Twilio posts the result to ``/ivr/presenter-gather/{session_id}/{field_name}``.
    Returns the Twilio call SID.
    """
    _require_twilio_voice()
    from twilio.rest import Client
    from xml.sax.saxutils import escape

    client = Client(config_models.TWILIO_ACCOUNT_SID, config_models.TWILIO_AUTH_TOKEN)
    intro = escape(_build_presenter_intro(field_name, intent=intent))
    safe_prompt = escape(field_prompt)
    action_url = (
        f"{callback_base_url.rstrip('/')}"
        f"/ivr/presenter-gather/{session_id}/{field_name}"
    )

    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Say voice="Polly.Joanna">{intro}</Say>'
        f'<Gather input="speech" timeout="15" speechTimeout="auto" '
        f'action="{escape(action_url)}" method="POST">'
        f'<Say voice="Polly.Joanna">{safe_prompt}</Say>'
        "</Gather>"
        '<Say voice="Polly.Joanna">No response received. Goodbye.</Say>'
        "</Response>"
    )

    call = client.calls.create(
        to=config_models.PRESENTER_PHONE_NUMBER,
        from_=config_models.TWILIO_AGENT_NUMBER,
        twiml=twiml,
    )
    logger.info(
        "Info-gather call placed sid=%s session=%s field=%s",
        call.sid, session_id, field_name,
    )
    return call.sid


def bridge_to_conference(
    conference_name: str,
    ivr_call_sid: str,
    presenter_phone: str,
    **_: Any,
) -> dict[str, str]:
    """Move the active IVR call and presenter into a Twilio conference.

    1. Updates the in-progress IVR call to join the conference.
    2. Dials the presenter into the same conference.
    Returns ``{conference_name, presenter_call_sid}``.
    """
    _require_twilio_voice()
    from twilio.rest import Client
    from xml.sax.saxutils import escape

    client = Client(config_models.TWILIO_ACCOUNT_SID, config_models.TWILIO_AUTH_TOKEN)
    safe_conf = escape(conference_name)

    ivr_conf_twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response><Dial>"
        f"<Conference>{safe_conf}</Conference>"
        "</Dial></Response>"
    )
    client.calls(ivr_call_sid).update(twiml=ivr_conf_twiml)
    logger.info("IVR call %s moved into conference %s", ivr_call_sid, conference_name)

    presenter_twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        '<Say voice="Polly.Joanna">'
        "Connecting you to the live call now."
        "</Say>"
        "<Dial>"
        f"<Conference>{safe_conf}</Conference>"
        "</Dial></Response>"
    )
    presenter_call = client.calls.create(
        to=presenter_phone or config_models.PRESENTER_PHONE_NUMBER,
        from_=config_models.TWILIO_AGENT_NUMBER,
        twiml=presenter_twiml,
    )
    logger.info(
        "Presenter dialed into conference %s (sid=%s)",
        conference_name, presenter_call.sid,
    )
    return {
        "conference_name": conference_name,
        "presenter_call_sid": presenter_call.sid,
    }


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
    """Escalation: SMS context + conference bridge (hard escalation).

    If ``twilio_call_sid`` is available the IVR call and presenter are
    joined in a Twilio conference so the human can speak directly on the
    line.  An SMS with the transcript link is sent first so the presenter
    has context before picking up.
    """
    url = transcript_url_for_session(session_id)
    logger.warning(
        "Escalation session=%s reason=%s call_sid=%s transcript=%s",
        session_id, reason, twilio_call_sid, url or "(no public base URL)",
    )

    twilio_ok = all(
        [
            config_models.TWILIO_ACCOUNT_SID,
            config_models.TWILIO_AUTH_TOKEN,
            config_models.PRESENTER_PHONE_NUMBER,
        ]
    )
    if not twilio_ok:
        return None

    parts = [f"Escalation {session_id}: {reason}."]
    if validated_fields:
        parts.append(f"Fields: {validated_fields}")
    if url:
        parts.append(f"Transcript: {url}")
    try:
        send_sms(" ".join(parts))
    except Exception as exc:
        logger.warning("Escalation SMS failed: %s", exc)

    if twilio_call_sid:
        conf = f"ivr_esc_{uuid.uuid4().hex[:12]}"
        presenter = (config_models.PRESENTER_PHONE_NUMBER or "").strip()
        raw = bridge_to_conference(conf, twilio_call_sid, presenter)
        return BridgeResult(
            conference_name=raw["conference_name"],
            presenter_call_sid=raw["presenter_call_sid"],
        )

    call_presenter(message=f"Escalation for session {session_id}. {reason}.")
    return None
