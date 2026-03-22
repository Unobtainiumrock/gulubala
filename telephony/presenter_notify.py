"""Twilio presenter notifications for IVR escalation and task completion."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import config.models as config_models
from telephony.twilio_client import bridge_to_conference, call_presenter, send_sms

logger = logging.getLogger("call_center.presenter_notify")

_MAX_SAY_CHARS = 500
_MAX_SMS_CHARS = 1400


@dataclass(frozen=True)
class BridgeResult:
    conference_name: str
    presenter_call_sid: str


def _notify_configured() -> bool:
    return bool(
        config_models.TWILIO_ACCOUNT_SID
        and config_models.TWILIO_AUTH_TOKEN
        and config_models.PRESENTER_PHONE_NUMBER,
    )


def _truncate(text: str, max_len: int) -> str:
    cleaned = text.strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3] + "..."


def _sanitize_say_text(text: str) -> str:
    """Twilio Say is sensitive to raw symbols; keep speech-friendly text."""
    cleaned = re.sub(r"[^\w\s.,;:!?'\-]", " ", text)
    return _truncate(re.sub(r"\s+", " ", cleaned), _MAX_SAY_CHARS)


def transcript_url_for_session(session_id: str) -> str | None:
    base = config_models.PUBLIC_API_BASE_URL.strip().rstrip("/")
    if not base:
        return None
    return f"{base}/transcript/{session_id}"


def notify_escalation(
    *,
    session_id: str,
    reason: str,
    validated_fields: dict[str, str],
    twilio_call_sid: str | None = None,
) -> BridgeResult | None:
    """Call + SMS the presenter; optionally bridge the live call into a conference."""
    if not _notify_configured():
        logger.info("Presenter escalation notify skipped (Twilio or presenter not configured).")
        return None

    fields_hint = ""
    if validated_fields:
        fields_hint = " Known fields: " + _truncate(
            ", ".join(f"{k}={v}" for k, v in validated_fields.items()),
            200,
        )
    sms_body = _truncate(
        f"[IVR agent] HELP session={session_id}\n{reason}{fields_hint}",
        _MAX_SMS_CHARS,
    )
    voice = _sanitize_say_text(
        f"IVR navigation agent needs help. {reason}. Session code {session_id[:8]}.",
    )

    try:
        send_sms(sms_body)
    except Exception as exc:
        logger.warning("Escalation SMS failed: %s", exc)

    try:
        call_presenter(voice)
    except Exception as exc:
        logger.warning("Escalation voice call to presenter failed: %s", exc)

    if not twilio_call_sid or not config_models.TWILIO_ESCALATION_BRIDGE:
        return None

    safe = re.sub(r"[^a-zA-Z0-9]", "", session_id)[:16] or "session"
    conference_name = f"ivr_esc_{safe}"
    try:
        info = bridge_to_conference(
            conference_name,
            twilio_call_sid,
            config_models.PRESENTER_PHONE_NUMBER,
        )
        return BridgeResult(
            conference_name=info["conference_name"],
            presenter_call_sid=info["presenter_call_sid"],
        )
    except Exception as exc:
        logger.warning("Conference bridge failed: %s", exc)
        return None


def notify_completion(
    *,
    session_id: str,
    summary: str | None,
    validated_fields: dict[str, str],
) -> None:
    """Call + SMS the presenter when the IVR task finished successfully."""
    if not _notify_configured():
        logger.info("Presenter completion notify skipped (Twilio or presenter not configured).")
        return

    link = transcript_url_for_session(session_id)
    summary_text = summary or "IVR navigation task completed."
    fields_hint = ""
    if validated_fields:
        fields_hint = " " + _truncate(
            ", ".join(f"{k}={v}" for k, v in validated_fields.items()),
            180,
        )

    sms_parts = [
        f"[IVR agent] DONE session={session_id}",
        summary_text + fields_hint,
    ]
    if link:
        sms_parts.append(f"Transcript: {link}")
    sms_body = _truncate("\n".join(sms_parts), _MAX_SMS_CHARS)

    voice = _sanitize_say_text(
        f"IVR task complete. {summary_text}{fields_hint}",
    )

    try:
        send_sms(sms_body)
    except Exception as exc:
        logger.warning("Completion SMS failed: %s", exc)

    try:
        call_presenter(voice)
    except Exception as exc:
        logger.warning("Completion voice call to presenter failed: %s", exc)
