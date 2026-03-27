"""Bland AI REST API client."""

from __future__ import annotations

import logging

import httpx

from config.models import BLAND_API_KEY

_logger = logging.getLogger(__name__)

_BASE_URL = "https://api.bland.ai/v1"


def _headers() -> dict[str, str]:
    if not BLAND_API_KEY:
        raise ValueError("BLAND_API_KEY is not set")
    return {
        "Authorization": BLAND_API_KEY,
        "Content-Type": "application/json",
    }


def send_call(
    phone_number: str,
    task: str,
    webhook_url: str,
    tools: list[dict],
    voice: str = "maya",
    max_duration: int = 300,
    transfer_phone_number: str | None = None,
    transfer_list: dict[str, str] | None = None,
) -> dict:
    """Place an outbound call via Bland AI.

    Args:
        transfer_phone_number: User's phone number to warm-transfer
            (patch in) when the agent escalates.
        transfer_list: Optional multi-target transfer map
            (e.g. ``{"default": "+1...", "billing": "+1..."}``)
            — overrides *transfer_phone_number* if a default is set.

    Returns the API response containing ``call_id`` and ``status``.
    """
    payload = {
        "phone_number": phone_number,
        "task": task,
        "webhook": webhook_url,
        "tools": tools,
        "voice": voice,
        "max_duration": max_duration,
    }
    if transfer_phone_number:
        payload["transfer_phone_number"] = transfer_phone_number
    if transfer_list:
        payload["transfer_list"] = transfer_list
    _logger.info("Placing Bland AI call to %s", phone_number)
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(f"{_BASE_URL}/calls", headers=_headers(), json=payload)
        resp.raise_for_status()
    data = resp.json()
    _logger.info("Bland AI call placed: call_id=%s", data.get("call_id"))
    return data


def get_call(call_id: str) -> dict:
    """Fetch call details and transcript for a given call."""
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(f"{_BASE_URL}/calls/{call_id}", headers=_headers())
        resp.raise_for_status()
    return resp.json()


def analyze_call(call_id: str, goal: str) -> dict:
    """Request Bland AI to analyze a completed call against a goal."""
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            f"{_BASE_URL}/calls/{call_id}/analyze",
            headers=_headers(),
            json={"goal": goal},
        )
        resp.raise_for_status()
    return resp.json()
