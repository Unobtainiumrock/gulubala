"""Text-to-speech helpers for the Callit-Dev demo."""

from __future__ import annotations

from datetime import datetime
from html import escape
import json
import re
from typing import Any

from client.eigen import generate_form
from config.models import DEMO_TTS_VOICE, HIGGS_TTS_MODEL


_DATE_PATTERNS = (
    "%m/%d/%Y",
    "%Y-%m-%d",
)


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

    def _speak_digits(match: re.Match[str]) -> str:
        digits = match.group(0)
        if len(digits) == 4:
            year = int(digits)
            if 1900 <= year <= 2099:
                return digits
        return " ".join(digits)

    # Speak compact digit runs one digit at a time for better clarity.
    normalized = re.sub(
        r"\b\d{4,}\b",
        _speak_digits,
        normalized,
    )
    return normalized


def _collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def _spell_identifier(token: str) -> str:
    parts = []
    for char in token:
        if char.isalnum():
            parts.append(char.upper() if char.isalpha() else char)
        elif char in {"-", "/"}:
            parts.append("dash")
    return " ".join(parts)


def _replace_dates(text: str) -> str:
    def _render(match: re.Match[str]) -> str:
        raw = match.group(0)
        for pattern in _DATE_PATTERNS:
            try:
                parsed = datetime.strptime(raw, pattern)
                return f"{parsed.strftime('%B')} {parsed.day}, {parsed.year}"
            except ValueError:
                continue
        return raw

    return re.sub(r"\b\d{1,2}/\d{1,2}/\d{4}\b|\b\d{4}-\d{2}-\d{2}\b", _render, text)


def _replace_emails(text: str) -> str:
    def _render(match: re.Match[str]) -> str:
        local = match.group(1)
        domain = match.group(2)
        spoken_local = (
            local.replace(".", " dot ")
            .replace("_", " underscore ")
            .replace("-", " dash ")
        )
        spoken_domain = domain.replace(".", " dot ").replace("-", " dash ")
        return _collapse_whitespace(f"{spoken_local} at {spoken_domain}")

    return re.sub(
        r"\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b", _render, text
    )


def _replace_labeled_identifiers(text: str) -> str:
    def _case_id(match: re.Match[str]) -> str:
        return f"Case number: {_spell_identifier(match.group(1))}"

    def _tracking(match: re.Match[str]) -> str:
        return f"{match.group(1)}{_spell_identifier(match.group(2))}"

    def _order(match: re.Match[str]) -> str:
        token = match.group(1)
        if any(char.isalpha() for char in token) and any(
            char.isdigit() for char in token
        ):
            return f"Order {_spell_identifier(token)}"
        return match.group(0)

    rewritten = re.sub(r"\bCase ID:\s*([A-Za-z0-9-]+)", _case_id, text)
    rewritten = re.sub(
        r"\b(tracking number is\s+)([A-Za-z0-9-]+)",
        _tracking,
        rewritten,
        flags=re.IGNORECASE,
    )
    rewritten = re.sub(r"\bOrder\s+([A-Za-z0-9-]{6,20})\b", _order, rewritten)
    rewritten = re.sub(r"\bUPS\b", "U P S", rewritten)
    return rewritten


def realize_spoken_text(text: str) -> str:
    """Build a deterministic spoken variant from the canonical response text."""
    spoken = _collapse_whitespace(text).strip()
    if not spoken:
        return ""

    spoken = _replace_dates(spoken)
    spoken = _replace_emails(spoken)
    spoken = _replace_labeled_identifiers(spoken)

    regex_replacements = (
        (r"\bThank you\.\s+", "Thanks. "),
        (r"\bI am going to\b", "I'll"),
        (r"\bI will\b", "I'll"),
        (r"\bI am\b", "I'm"),
        (r"\bI have that information\.", "I've got that information."),
        (r"\bPlease continue\.", "Go ahead."),
    )
    for pattern, replacement in regex_replacements:
        spoken = re.sub(pattern, replacement, spoken)

    spoken = normalize_tts_text(spoken)
    return _collapse_whitespace(spoken)


def _build_ssml_from_spoken_text(spoken_text: str) -> str:
    if not spoken_text:
        return "<speak></speak>"

    sentences = [
        segment.strip()
        for segment in re.split(r"(?<=[.!?])\s+", spoken_text)
        if segment.strip()
    ]
    if not sentences:
        sentences = [spoken_text]

    rendered = []
    for sentence in sentences:
        escaped_sentence = escape(sentence)
        escaped_sentence = re.sub(r",\s+", ', <break time="150ms"/> ', escaped_sentence)
        rendered.append(escaped_sentence)

    body = ' <break time="350ms"/> '.join(rendered)
    return f'<speak><prosody rate="95%">{body}</prosody></speak>'


def build_ssml(text: str) -> str:
    """Wrap a response in light SSML so speech output sounds less mechanical."""
    try:
        spoken_text = realize_spoken_text(text)
    except Exception:
        spoken_text = _collapse_whitespace(text).strip()
    return _build_ssml_from_spoken_text(spoken_text)


def build_voice_response(
    session_id: str, text: str, voice: str = DEMO_TTS_VOICE
) -> dict[str, Any] | None:
    """Return a voice-friendly envelope with normalized text and voice provider payload."""
    if not text.strip():
        return None

    fallback_text = _collapse_whitespace(text).strip()
    try:
        spoken_text = realize_spoken_text(text)
    except Exception:
        spoken_text = fallback_text
    ssml = _build_ssml_from_spoken_text(spoken_text)
    return {
        "text": text,
        "spoken_text": spoken_text,
        "ssml": ssml,
        "voice_provider": {
            "type": "assistant_output",
            "session_id": session_id,
            "text": spoken_text,
            "ssml": ssml,
            "voice": voice,
            "barge_in": True,
        },
    }


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
