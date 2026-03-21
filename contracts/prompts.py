"""Versioned prompt contracts and response parsing helpers."""

from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel, Field

PROMPT_VERSION = "2026-03-21"
T = TypeVar("T", bound=BaseModel)


class IntentExtractionResponse(BaseModel):
    intent: str
    confidence: float = Field(ge=0.0, le=1.0)
    needs_disambiguation: bool = False
    reason: str | None = None


class FieldExtractionResponse(BaseModel):
    found: bool
    value: str | None = None


class MultiFieldExtractionResponse(BaseModel):
    fields: dict[str, str | None]


class EscalationSummaryResponse(BaseModel):
    summary: str


def _find_json_payload(raw: str) -> str:
    raw = raw.strip()
    try:
        json.loads(raw)
        return raw
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = raw[start : end + 1]
        json.loads(candidate)
        return candidate
    raise ValueError("No JSON object found in model response")


def parse_contract(raw: str, model_cls: type[T]) -> T:
    payload = _find_json_payload(raw)
    return model_cls.model_validate_json(payload)


def build_intent_prompt(supported_intents: list[str]) -> str:
    return (
        f"[prompt_contract={PROMPT_VERSION}:intent_extraction]\n"
        "You are an intent classifier for a call center.\n"
        f"Supported intents: {json.dumps(supported_intents)}\n"
        "Return JSON with keys: intent, confidence, needs_disambiguation, reason.\n"
        'If unsupported, set intent to "unsupported".'
    )


def build_field_extraction_prompt(field_name: str, field_type: str) -> str:
    return (
        f"[prompt_contract={PROMPT_VERSION}:field_extraction]\n"
        f"Extract the value for field '{field_name}' with type '{field_type}'.\n"
        "Return JSON with keys: found, value.\n"
        "If no value is present, return {\"found\": false, \"value\": null}."
    )


def build_multi_field_extraction_prompt(fields: list[tuple[str, str]]) -> str:
    field_lines = "\n".join(f"- {name} (type: {ftype})" for name, ftype in fields)
    example = json.dumps({"fields": {name: "..." for name, _ in fields}})
    return (
        f"[prompt_contract={PROMPT_VERSION}:multi_field_extraction]\n"
        "Extract values for the following fields from the user's message.\n"
        "For each field, return the extracted value or null if not present.\n\n"
        f"Fields:\n{field_lines}\n\n"
        f"Return ONLY valid JSON like: {example}\n"
        "Use null for any field not found in the message."
    )


def build_escalation_summary_prompt(summary_payload: dict[str, Any]) -> str:
    return (
        f"[prompt_contract={PROMPT_VERSION}:escalation_summary]\n"
        "Generate a concise human handoff summary.\n"
        "Return JSON with key: summary.\n"
        f"Payload: {json.dumps(summary_payload)}"
    )
