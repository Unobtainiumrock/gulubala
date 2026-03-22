"""Versioned prompt contracts and response parsing helpers."""

from __future__ import annotations

import json
import re
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
        "request_info",
        "escalate",
        "complete",
    ]
    dtmf_digits: str | None = None
    speech_text: str | None = None
    reasoning: str | None = None
    escalation_reason: str | None = None
    completion_summary: str | None = None
    requested_field: str | None = None
    field_prompt: str | None = None


def _strip_json_trailing_commas(s: str) -> str:
    """Remove invalid JSON trailing commas before ``}`` or ``]`` (common LLM mistake)."""
    prev = None
    out = s
    while prev != out:
        prev = out
        out = re.sub(r",(\s*})", r"\1", out)
        out = re.sub(r",(\s*\])", r"\1", out)
    return out


def _extract_first_balanced_object(raw: str) -> str | None:
    """Return the first ``{...}`` span with balanced braces, respecting string escapes."""
    start = raw.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    i = start
    while i < len(raw):
        c = raw[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            i += 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return raw[start : i + 1]
        i += 1
    return None


def _find_json_payload(raw: str) -> str:
    """Parse JSON from model output; tolerate markdown, trailing commas, and extra text."""
    raw = raw.strip()
    candidates: list[str] = []
    if raw:
        candidates.append(raw)

    balanced = _extract_first_balanced_object(raw)
    if balanced:
        candidates.append(balanced)

    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(raw[start : end + 1])

    seen: set[str] = set()
    for cand in candidates:
        c = cand.strip()
        if not c or c in seen:
            continue
        seen.add(c)
        for variant in (c, _strip_json_trailing_commas(c)):
            if not variant:
                continue
            try:
                json.loads(variant)
                return variant
            except json.JSONDecodeError:
                continue
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
        "Do not use trailing commas before closing braces. "
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
        "completion_summary": None,
        "requested_field": None,
        "field_prompt": None,
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
        "- request_info: The IVR is asking for information you do NOT have in your "
        "available fields. Set requested_field to the field name (e.g. 'security_pin') "
        "and field_prompt to a plain-English question to ask the human "
        "(e.g. 'What is the security PIN on your account?'). "
        "The system will call the human, ask the question, and give you the answer.",
        "- escalate: A live human agent has joined the call OR you are completely stuck "
        "and the human must speak on the line. This bridges the human into the call "
        "via conference. Only use this when a real human-to-human conversation is needed.",
        "- complete: The caller's task is finished (IVR confirmed success or final step done); "
        "set completion_summary to a short outcome phrase\n",
        f"Return ONLY valid JSON like: {example}",
    ]
    return "\n".join(parts)
