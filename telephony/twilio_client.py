"""Outbound Twilio calls that connect a callee to the Pipecat WebSocket media stream."""

from __future__ import annotations

import logging
import re

from twilio.rest import Client

from config.models import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_AGENT_NUMBER

logger = logging.getLogger(__name__)

# Twilio sendDigits: 0-9, w/W (short pause), * #
_DTMF_ALLOWED = re.compile(r"^[0-9wW*#]+$")


def _validate_dtmf_digits(raw: str) -> str:
    """Return normalized DTMF digits for safe embedding in TwiML."""
    digits = "".join(str(raw).split())
    if not digits:
        raise ValueError("DTMF sequence must be non-empty")
    if not _DTMF_ALLOWED.fullmatch(digits):
        raise ValueError("DTMF may only contain 0-9, w, W, *, #")
    return digits


def initiate_stream_call(*, to: str, stream_url: str) -> str:
    """Dial *to* and bridge audio to the WebSocket server at *stream_url* (wss://...).

    ``stream_url`` must be reachable from Twilio (e.g. ngrok tunnel to ``PIPELINE_WS_PORT``).
    Uses ``TWILIO_AGENT_NUMBER`` as the caller ID.
    """
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_AGENT_NUMBER]):
        raise RuntimeError(
            "TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_AGENT_NUMBER must be set "
            "for outbound stream calls.",
        )

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{stream_url}" />
  </Connect>
</Response>"""

    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    call = client.calls.create(
        to=to,
        from_=TWILIO_AGENT_NUMBER,
        twiml=twiml,
    )
    logger.info("Started outbound call sid=%s to=%s", call.sid, to)
    return call.sid
