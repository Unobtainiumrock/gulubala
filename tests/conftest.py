"""Shared test helpers."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dialogue.manager import WorkflowEngine
from services.orchestrator import CallCenterService
from services.session_store import InMemorySessionStore


def stub_field_extractor(field, utterance: str) -> str | None:
    text = utterance.strip()
    digits = re.sub(r"[^\d]", "", text)

    if field.name in {"account_id", "account_number", "verification_code", "zip_code"}:
        return digits or None
    if field.name == "charge_amount":
        match = re.search(r"\$?\d+(?:\.\d{1,2})?", text)
        return match.group(0) if match else None
    if field.name == "charge_date":
        match = re.search(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", text)
        return match.group(0) if match else None
    if field.name == "order_number":
        match = re.search(r"[A-Za-z0-9\-]{6,20}", text)
        return match.group(0) if match else None
    if field.name in {"dispute_reason", "cancellation_reason", "new_value"}:
        return text if digits != text or not digits else None
    if field.name == "field_to_update":
        lowered = text.lower()
        for item in ("address", "phone", "email", "name"):
            if item in lowered:
                return item
        return None
    if field.name == "confirm_cancel":
        return text.lower() if text else None
    if field.name in {"email", "callback_number", "merchant_name", "reference_number"}:
        return text or None
    return None


def stub_multi_field_extractor(fields, utterance: str) -> dict[str, str]:
    """Extract multiple fields from a combined utterance.

    Splits by whitespace and tries each token per field so that
    "12345678 03/01/2026 $95.00" correctly maps account_number→12345678,
    charge_date→03/01/2026, charge_amount→$95.00 instead of concatenating
    all digits together.  Free-text fields (reasons) get whatever tokens
    remain after structured fields are consumed.
    """
    tokens = utterance.strip().split()
    used: set[int] = set()
    result: dict[str, str] = {}

    # Structured fields first (order, amount, date, digit-based IDs)
    free_text_fields = {"dispute_reason", "cancellation_reason", "new_value"}
    for field in fields:
        if field.name in free_text_fields:
            continue
        for i, token in enumerate(tokens):
            if i in used:
                continue
            value = stub_field_extractor(field, token)
            if value is not None:
                result[field.name] = value
                used.add(i)
                break

    # Free-text fields get remaining unconsumed tokens
    for field in fields:
        if field.name not in free_text_fields:
            continue
        remaining = " ".join(t for i, t in enumerate(tokens) if i not in used)
        if remaining:
            value = stub_field_extractor(field, remaining)
            if value is not None:
                result[field.name] = value

    return result


def make_service(monkeypatch: pytest.MonkeyPatch, intent: str, confidence: float = 0.95) -> CallCenterService:
    monkeypatch.setattr(
        "services.orchestrator.classify_intent",
        lambda utterance: {
            "intent": intent,
            "confidence": confidence,
            "needs_disambiguation": False,
            "escalate": False,
            "reason": None,
        },
    )
    engine = WorkflowEngine(
        field_extractor=stub_field_extractor,
        multi_field_extractor=stub_multi_field_extractor,
        summary_builder=lambda payload: "Escalation summary.",
    )
    return CallCenterService(InMemorySessionStore(), engine=engine)


@pytest.fixture
def password_reset_service(monkeypatch: pytest.MonkeyPatch) -> CallCenterService:
    return make_service(monkeypatch, "password_reset")


@pytest.fixture
def billing_service(monkeypatch: pytest.MonkeyPatch) -> CallCenterService:
    return make_service(monkeypatch, "billing_dispute")
