"""Structured logging and privacy helpers."""

from __future__ import annotations

import json
import logging
from typing import Any

from config.models import REDACT_FIELD_HINTS, TRANSCRIPT_CONTEXT_TURNS, TRANSCRIPT_RETENTION_ENABLED
from contracts.models import SessionState

_LOGGER = logging.getLogger("call_center")
if not _LOGGER.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    _LOGGER.addHandler(handler)
_LOGGER.setLevel(logging.INFO)


def _is_sensitive_field(field_name: str) -> bool:
    lowered = field_name.lower()
    return any(hint in lowered for hint in REDACT_FIELD_HINTS)


def _redact_value(value: Any) -> Any:
    if value is None:
        return None
    string_value = str(value)
    if len(string_value) <= 4:
        return "***"
    return f"{string_value[:2]}***{string_value[-2:]}"


def redact_mapping(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _redact_value(value) if _is_sensitive_field(key) else value
        for key, value in values.items()
    }


def serialize_state_for_logs(session: SessionState) -> dict[str, Any]:
    payload = session.model_dump()
    payload["collected_fields"] = redact_mapping(session.collected_fields)
    payload["validated_fields"] = redact_mapping(session.validated_fields)
    if TRANSCRIPT_RETENTION_ENABLED:
        history = payload["conversation_history"][-TRANSCRIPT_CONTEXT_TURNS:]
        payload["conversation_history"] = history
    else:
        payload["conversation_history"] = []
    return payload


def log_event(event_type: str, session: SessionState, **data: Any) -> None:
    payload = {
        "event": event_type,
        "session_id": session.session_id,
        "intent": session.intent,
        "escalate": session.escalate,
        "escalation_reason": session.escalation_reason,
        "state": serialize_state_for_logs(session),
        "data": data,
    }
    _LOGGER.info(json.dumps(payload, sort_keys=True, default=str))
