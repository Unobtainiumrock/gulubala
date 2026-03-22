"""Seeded demo scenarios and presentation copy."""

from __future__ import annotations

from copy import deepcopy

from config.models import DEMO_BRAND_NAME

_SCENARIOS = {
    "password_reset": {
        "id": "password_reset",
        "title": "Access Recovery",
        "intent": "password_reset",
        "tagline": "Guided troubleshooting with identity verification",
        "summary": "A caller cannot access their account, and Callit-Dev gathers the account number and verification code before automating the reset.",
        "opening_message": (
            f"Welcome to {DEMO_BRAND_NAME}. I can help you restore access to your account today. "
            "To begin, please say or enter your account number now."
        ),
        "seed_script": [
            {"speaker": "caller", "line": "My account number is 12345678."},
            {"speaker": "caller", "line": "The verification code is 123456."},
        ],
        "demo_goal": "Show a workflow that needs more information before it can complete.",
    },
    "cancel_service": {
        "id": "cancel_service",
        "title": "Subscription Cancellation",
        "intent": "cancel_service",
        "tagline": "Smooth automation from request to completion",
        "summary": "A caller asks to cancel a subscription, provides a short reason, confirms the request, and the workflow completes successfully.",
        "opening_message": (
            f"Welcome to {DEMO_BRAND_NAME}. I can help with your subscription request. "
            "To get started, please say or enter your account number."
        ),
        "seed_script": [
            {"speaker": "caller", "line": "My account number is 12345678."},
            {"speaker": "caller", "line": "I am consolidating vendors."},
            {"speaker": "caller", "line": "Yes, please cancel it."},
        ],
        "demo_goal": "Show a streamlined workflow that collects the minimum required information and completes automatically.",
    },
}


def list_demo_scenarios() -> list[dict]:
    return [deepcopy(value) for value in _SCENARIOS.values()]


def get_demo_scenario(scenario_id: str) -> dict:
    scenario = _SCENARIOS.get(scenario_id)
    if scenario is None:
        raise KeyError(f"Unknown demo scenario '{scenario_id}'")
    return deepcopy(scenario)
