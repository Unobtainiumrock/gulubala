"""Layer 1: Intent Router — classify caller utterance into a workflow intent."""

from client.eigen import chat_completion
from config.models import HIGGS_CHAT_MODEL, INTENT_CONFIDENCE_THRESHOLD
from contracts.prompts import IntentExtractionResponse, build_intent_prompt, parse_contract
from workflows.registry import list_intents

SUPPORTED_INTENTS = list_intents()
INTENT_SYSTEM_PROMPT = build_intent_prompt(SUPPORTED_INTENTS)


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
        parsed = parse_contract(raw, IntentExtractionResponse)
        result = parsed.model_dump()
    except Exception:
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
        or confidence < INTENT_CONFIDENCE_THRESHOLD
    )
    if result.get("needs_disambiguation"):
        result["escalate"] = True
        result["reason"] = result.get("reason") or "needs_disambiguation"

    if intent not in SUPPORTED_INTENTS and intent != "unsupported":
        result["intent"] = "unsupported"
        result["escalate"] = True
        result["reason"] = result.get("reason") or "unsupported_intent"

    return result
