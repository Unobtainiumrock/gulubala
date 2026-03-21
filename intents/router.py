"""Layer 1: Intent Router — classify caller utterance into a workflow intent."""

import json
from client.eigen import chat_completion
from config.models import HIGGS_CHAT_MODEL, INTENT_CONFIDENCE_THRESHOLD, DISAMBIGUATION_THRESHOLD

SUPPORTED_INTENTS = [
    "password_reset",
    "billing_dispute",
    "update_profile",
    "order_status",
    "cancel_service",
]

INTENT_SYSTEM_PROMPT = f"""You are an intent classifier for a call center. Given a caller's statement, classify it into exactly one of these intents:

{json.dumps(SUPPORTED_INTENTS)}

Respond with ONLY valid JSON in this format:
{{"intent": "<intent_name>", "confidence": <0.0-1.0>, "needs_disambiguation": <true/false>, "reason": "<brief explanation>"}}

If the caller's issue does not match any intent, use intent "unsupported".
If multiple intents are plausible, set needs_disambiguation to true and pick the most likely one."""


def classify_intent(transcript: str) -> dict:
    """Classify a transcript into a supported workflow intent.

    Returns:
        dict with keys: intent, confidence, needs_disambiguation, escalate, reason
    """
    messages = [
        {"role": "system", "content": INTENT_SYSTEM_PROMPT},
        {"role": "user", "content": transcript},
    ]

    raw = chat_completion(
        model=HIGGS_CHAT_MODEL,
        messages=messages,
        temperature=0.1,
        max_tokens=256,
    )

    try:
        result = json.loads(raw.strip())
    except json.JSONDecodeError:
        return {
            "intent": "unsupported",
            "confidence": 0.0,
            "needs_disambiguation": False,
            "escalate": True,
            "reason": f"Failed to parse intent response: {raw[:200]}",
        }

    confidence = result.get("confidence", 0.0)
    intent = result.get("intent", "unsupported")

    result["escalate"] = (
        intent == "unsupported"
        or confidence < DISAMBIGUATION_THRESHOLD
    )

    if intent not in SUPPORTED_INTENTS and intent != "unsupported":
        result["intent"] = "unsupported"
        result["escalate"] = True

    return result
