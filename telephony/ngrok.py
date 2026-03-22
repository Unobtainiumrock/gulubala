"""Best-effort ngrok tunnel detection and Twilio voice webhook sync."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


def _ngrok_https_url() -> str | None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=2) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    for tunnel in data.get("tunnels", []):
        if tunnel.get("proto") == "https":
            return tunnel.get("public_url")
    return None


def auto_sync() -> dict[str, Any] | None:
    """If ngrok is running locally, return its public HTTPS URL and optionally sync Twilio.

    Sets the incoming voice webhook on a Twilio phone number when
    ``TWILIO_VOICE_NUMBER_SID`` is set (Console → number → sid).
    """
    public = _ngrok_https_url()
    if not public:
        return None

    voice_url = f"{public.rstrip('/')}/ivr/incoming"
    result: dict[str, Any] = {"voice_url": voice_url, "synced": False}

    number_sid = os.environ.get("TWILIO_VOICE_NUMBER_SID", "").strip()
    if not number_sid:
        logger.info("ngrok detected (%s); set TWILIO_VOICE_NUMBER_SID to auto-sync Twilio.", public)
        return result

    try:
        from twilio.rest import Client

        from config.models import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN

        if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
            logger.warning("Twilio credentials missing; skipping webhook sync.")
            return result

        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.incoming_phone_numbers(number_sid).update(voice_url=voice_url)
        result["synced"] = True
        logger.info("Twilio voice webhook updated to %s", voice_url)
    except Exception as exc:
        logger.warning("Twilio webhook sync failed: %s", exc)

    return result
