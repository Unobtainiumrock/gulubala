"""Timed IVR utterances for scripted demos (no dependency on external IVR audio).

Each entry is ``(delay_seconds_after_previous, text_spoken_by_the_phone_tree)``.
Delays give the navigator time to send DTMF / TTS between prompts.
"""

from __future__ import annotations

# cancel_service: root -> 1 billing -> 2 cancel -> account -> reason -> confirm -> "human"
CANCEL_SERVICE_LINES: list[tuple[float, str]] = [
    (
        4.0,
        "Thank you for calling Acme Corp. Press 1 for billing, 2 for account services, "
        "or 3 for order support.",
    ),
    (8.0, "For a billing dispute, press 1. To cancel your service, press 2."),
    (8.0, "Please hold while I connect you to our cancellation specialist."),
    (
        10.0,
        "Thank you. Please say or enter your account number so I can locate the subscription.",
    ),
    (14.0, "Thank you. What is the main reason you would like to cancel today?"),
    (
        16.0,
        "To confirm, would you like me to cancel the subscription now? Please say yes or no.",
    ),
    (
        14.0,
        "Hi, this is Alex from Acme retention. I see you're canceling. "
        "What can I do to keep you as a customer?",
    ),
]

# password_reset: root -> 2 account -> 1 password reset -> account -> code (optional gather)
PASSWORD_RESET_LINES: list[tuple[float, str]] = [
    (
        4.0,
        "Thank you for calling Acme Corp. Press 1 for billing, 2 for account services, "
        "or 3 for order support.",
    ),
    (8.0, "For password reset help, press 1. To update your profile, press 2."),
    (8.0, "Please hold while I connect you to our password reset specialist."),
    (
        10.0,
        "Please say or enter your account number now.",
    ),
    (
        14.0,
        "Thank you. Please say or enter the 6-digit verification code we sent to your phone.",
    ),
]

DEMO_IVR_SCRIPTS: dict[str, list[tuple[float, str]]] = {
    "cancel_service": CANCEL_SERVICE_LINES,
    "password_reset": PASSWORD_RESET_LINES,
}


def get_demo_ivr_script(scenario: str) -> list[tuple[float, str]]:
    """Return script lines for *scenario* or raise ``KeyError``."""
    if scenario not in DEMO_IVR_SCRIPTS:
        raise KeyError(f"No demo IVR script for scenario {scenario!r}")
    return DEMO_IVR_SCRIPTS[scenario]
