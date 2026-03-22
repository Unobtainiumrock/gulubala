"""Versioned prompt contracts and response parsing helpers."""

from __future__ import annotations

import json
from typing import Any, Literal, TypeVar

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


class IvrClassificationResponse(BaseModel):
    category: Literal[
        "menu",
        "info_request",
        "confirmation",
        "transfer",
        "hold",
        "error",
        "human_agent",
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    options: dict[str, str] | None = None
    requested_info: str | None = None
    transcript_snippet: str | None = None


class IvrActionResponse(BaseModel):
    action: Literal[
        "send_dtmf",
        "speak",
        "wait",
        "escalate",
    ]
    dtmf_digits: str | None = None
    speech_text: str | None = None
    reasoning: str | None = None
    escalation_reason: str | None = None


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


def build_ivr_classification_prompt() -> str:
    categories = ["menu", "info_request", "confirmation", "transfer", "hold", "error", "human_agent"]
    example = json.dumps({
        "category": "menu",
        "confidence": 0.95,
        "options": {"1": "Billing", "2": "Account services"},
        "requested_info": None,
        "transcript_snippet": "Press 1 for billing",
    })
    return (
        f"[prompt_contract={PROMPT_VERSION}:ivr_classification]\n"
        "You are analyzing a transcript of what an IVR phone system just said.\n"
        "Classify the IVR prompt into one of these categories:\n"
        "- menu: The IVR is presenting numbered options (Press 1 for X, Press 2 for Y)\n"
        "- info_request: The IVR is asking for specific information (account number, date of birth, etc.)\n"
        "- confirmation: The IVR is asking for a yes/no confirmation\n"
        "- transfer: The IVR is announcing a transfer to another department or agent\n"
        "- hold: The IVR is asking to wait or hold music is playing\n"
        "- error: The IVR is reporting an error or saying input was invalid\n"
        "- human_agent: A live human agent has joined the call\n\n"
        f"Categories: {json.dumps(categories)}\n"
        "If category is 'menu', extract the available options as a digit-to-label mapping.\n"
        "If category is 'info_request', identify what information is being requested.\n"
        f"Return ONLY valid JSON like: {example}"
    )


def build_ivr_action_prompt(
    task_description: str,
    current_node_id: str,
    classification_category: str,
    available_fields: dict[str, str],
    menu_options: dict[str, str] | None = None,
    recent_transcript: list[dict[str, str]] | None = None,
) -> str:
    example = json.dumps({
        "action": "send_dtmf",
        "dtmf_digits": "1",
        "speech_text": None,
        "reasoning": "Selecting billing menu to reach billing dispute",
        "escalation_reason": None,
    })
    parts = [
        f"[prompt_contract={PROMPT_VERSION}:ivr_action]",
        "You are an AI agent navigating an IVR phone system on behalf of a caller.\n",
        f"Your task: {task_description}",
        f"Current position in call tree: {current_node_id}",
        f"IVR prompt type: {classification_category}",
        f"Information you have available: {json.dumps(available_fields)}",
    ]
    if menu_options:
        parts.append(f"Menu options on this node: {json.dumps(menu_options)}")
    if recent_transcript:
        parts.append(f"Recent conversation:\n{json.dumps(recent_transcript, indent=2)}")
    parts += [
        "\nDecide what to do next:",
        "- send_dtmf: Press a digit to select a menu option",
        "- speak: Say something to answer a question or provide information",
        "- wait: Stay silent and listen for more",
        "- escalate: You are stuck and need human help\n",
        f"Return ONLY valid JSON like: {example}",
    ]
    return "\n".join(parts)
