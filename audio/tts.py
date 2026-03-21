"""Text-to-speech helpers for the Callit-Dev demo."""

from __future__ import annotations

import json
import re

from client.eigen import generate_form
from config.models import DEMO_TTS_VOICE, HIGGS_TTS_MODEL


def normalize_tts_text(text: str) -> str:
    """Rewrite phrases that TTS models tend to pronounce poorly."""
    normalized = text
    replacements = {
        "account ID": "account number",
        "Account ID": "account number",
        "6-digit": "six-digit",
        "8 to 12": "eight to twelve",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)

    # Speak compact digit runs one digit at a time for better clarity.
    normalized = re.sub(
        r"\b\d{4,}\b",
        lambda match: " ".join(match.group(0)),
        normalized,
    )
    return normalized


def synthesize_speech(text: str, voice: str = DEMO_TTS_VOICE) -> bytes:
    """Generate WAV audio for a short assistant response."""
    normalized_text = normalize_tts_text(text)
    sampling = json.dumps({"temperature": 0.85, "top_p": 0.95, "top_k": 50})
    return generate_form(
        model=HIGGS_TTS_MODEL,
        text=normalized_text,
        voice=voice,
        stream="false",
        sampling=sampling,
        expect_json=False,
    )
