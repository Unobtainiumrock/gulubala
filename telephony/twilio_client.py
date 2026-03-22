"""Twilio REST API helper for outbound calls, SMS, and conferencing."""

from __future__ import annotations

from typing import Any

from twilio.rest import Client
from twilio.twiml.voice_response import Connect, Dial, VoiceResponse

from config.models import (
    PRESENTER_PHONE_NUMBER,
    TWILIO_ACCOUNT_SID,
    TWILIO_AGENT_NUMBER,
    TWILIO_AUTH_TOKEN,
)

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
            raise RuntimeError(
                "TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set in the environment."
            )
        _client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    return _client


def initiate_stream_call(
    to: str,
    stream_url: str,
    *,
    from_: str = TWILIO_AGENT_NUMBER,
    status_callback: str | None = None,
) -> str:
    """Place an outbound call that connects bidirectional audio to a WebSocket.

    Args:
        to: Destination phone number (E.164).
        stream_url: ``wss://`` URL for the Pipecat media stream endpoint.
        from_: Caller ID (defaults to the agent number).
        status_callback: Optional URL for call status webhooks.

    Returns:
        The Twilio ``CallSid`` of the new call.
    """
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=stream_url)
    response.append(connect)

    kwargs: dict[str, Any] = {
        "to": to,
        "from_": from_,
        "twiml": str(response),
    }
    if status_callback:
        kwargs["status_callback"] = status_callback
        kwargs["status_callback_event"] = ["initiated", "ringing", "answered", "completed"]

    call = _get_client().calls.create(**kwargs)
    return call.sid


def send_dtmf(call_sid: str, digits: str) -> None:
    """Send DTMF tones to an active call.

    Args:
        call_sid: The ``CallSid`` of the target call.
        digits: DTMF digits to send (0-9, *, #, w for 0.5s pause).
    """
    twiml = f'<Response><Play digits="{digits}"></Play></Response>'
    _get_client().calls(call_sid).update(twiml=twiml)


def send_sms(
    body: str,
    to: str = PRESENTER_PHONE_NUMBER,
    from_: str = TWILIO_AGENT_NUMBER,
) -> str:
    """Send an SMS message.

    Returns:
        The Twilio ``MessageSid``.
    """
    message = _get_client().messages.create(body=body, to=to, from_=from_)
    return message.sid


def call_presenter(
    message: str,
    *,
    to: str = PRESENTER_PHONE_NUMBER,
    from_: str = TWILIO_AGENT_NUMBER,
) -> str:
    """Place a call to the presenter and speak a message via TTS.

    Returns:
        The Twilio ``CallSid``.
    """
    response = VoiceResponse()
    response.say(message, voice="Polly.Joanna")
    response.pause(length=1)
    response.say("Goodbye.", voice="Polly.Joanna")

    call = _get_client().calls.create(to=to, from_=from_, twiml=str(response))
    return call.sid


def create_conference(
    conference_name: str,
    *participants: str,
    from_: str = TWILIO_AGENT_NUMBER,
) -> list[str]:
    """Create a conference and dial participants into it.

    Args:
        conference_name: Friendly name for the conference room.
        participants: Phone numbers to dial into the conference.
        from_: Caller ID for outbound legs.

    Returns:
        List of ``CallSid`` values for each participant leg.
    """
    client = _get_client()
    sids: list[str] = []

    for number in participants:
        response = VoiceResponse()
        dial = Dial()
        dial.conference(
            conference_name,
            start_conference_on_enter=True,
            end_conference_on_exit=False,
        )
        response.append(dial)

        call = client.calls.create(to=number, from_=from_, twiml=str(response))
        sids.append(call.sid)

    return sids


def bridge_to_conference(
    conference_name: str,
    ivr_call_sid: str,
    presenter_number: str = PRESENTER_PHONE_NUMBER,
    from_: str = TWILIO_AGENT_NUMBER,
) -> dict[str, str]:
    """Bridge an existing IVR call and the presenter into a conference.

    Moves the IVR call leg into a conference room, then dials the presenter
    into the same room.

    Returns:
        Dict with ``presenter_call_sid`` and ``conference_name``.
    """
    client = _get_client()

    conf_twiml = VoiceResponse()
    dial = Dial()
    dial.conference(
        conference_name,
        start_conference_on_enter=True,
        end_conference_on_exit=True,
    )
    conf_twiml.append(dial)
    client.calls(ivr_call_sid).update(twiml=str(conf_twiml))

    presenter_twiml = VoiceResponse()
    p_dial = Dial()
    p_dial.conference(
        conference_name,
        start_conference_on_enter=True,
        end_conference_on_exit=True,
    )
    presenter_twiml.append(p_dial)

    presenter_call = client.calls.create(
        to=presenter_number,
        from_=from_,
        twiml=str(presenter_twiml),
    )

    return {
        "presenter_call_sid": presenter_call.sid,
        "conference_name": conference_name,
    }
