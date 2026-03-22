"""Detect ngrok tunnel URL and sync Twilio webhook configuration."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from twilio.rest import Client

from config.models import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_IVR_NUMBER

logger = logging.getLogger(__name__)

NGROK_API = "http://127.0.0.1:4040/api/tunnels"
IVR_VOICE_PATH = "/ivr/incoming"
IVR_STATUS_PATH = "/ivr/status-callback"

_MAX_RETRIES = 10
_RETRY_DELAY_SECONDS = 1.0


def detect_ngrok_url(*, retries: int = _MAX_RETRIES) -> str | None:
    """Poll ngrok's local API until an HTTPS tunnel is found.

    Returns the public HTTPS base URL (e.g. ``https://abc.ngrok-free.app``)
    or ``None`` if ngrok is unreachable after *retries* attempts.
    """
    for attempt in range(1, retries + 1):
        try:
            resp = httpx.get(NGROK_API, timeout=2)
            resp.raise_for_status()
            tunnels: list[dict[str, Any]] = resp.json().get("tunnels", [])
            for tunnel in tunnels:
                url: str = tunnel.get("public_url", "")
                if url.startswith("https://"):
                    return url
        except (httpx.HTTPError, httpx.ConnectError, KeyError):
            pass
        if attempt < retries:
            time.sleep(_RETRY_DELAY_SECONDS)
    return None


def sync_twilio_webhook(ngrok_base_url: str) -> dict[str, str]:
    """Update the Twilio IVR number's voice webhook to point at *ngrok_base_url*.

    Returns a dict with the configured ``voice_url`` and ``status_callback``.

    Raises ``RuntimeError`` if Twilio credentials or IVR number are missing.
    """
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
        raise RuntimeError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set.")
    if not TWILIO_IVR_NUMBER:
        raise RuntimeError("TWILIO_IVR_NUMBER must be set.")

    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

    numbers = client.incoming_phone_numbers.list(phone_number=TWILIO_IVR_NUMBER)
    if not numbers:
        raise RuntimeError(f"No Twilio number matching {TWILIO_IVR_NUMBER} found on this account.")

    phone = numbers[0]
    voice_url = f"{ngrok_base_url.rstrip('/')}{IVR_VOICE_PATH}"
    status_url = f"{ngrok_base_url.rstrip('/')}{IVR_STATUS_PATH}"

    phone.update(
        voice_url=voice_url,
        voice_method="POST",
        status_callback=status_url,
        status_callback_method="POST",
    )

    logger.info("Twilio IVR webhook synced: voice_url=%s status_callback=%s", voice_url, status_url)
    return {"voice_url": voice_url, "status_callback": status_url}


def auto_sync() -> dict[str, str] | None:
    """Convenience: detect ngrok then sync Twilio. Returns URLs or None."""
    url = detect_ngrok_url()
    if url is None:
        logger.warning("ngrok tunnel not detected; Twilio webhooks NOT updated.")
        return None
    return sync_twilio_webhook(url)
