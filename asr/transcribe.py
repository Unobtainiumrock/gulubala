"""Stage 1: Audio transcription via Eigen generate endpoint."""

from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Any

from client.eigen import generate_file
from config.models import ASR_LANGUAGE, HIGGS_ASR_MODEL


def _extract_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()

    if not isinstance(payload, dict):
        raise ValueError(f"Unsupported ASR response type: {type(payload).__name__}")

    for key in ("text", "transcript", "transcription", "output", "response"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("text", "transcript", "output"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    predictions = payload.get("predictions")
    if isinstance(predictions, list) and predictions:
        first = predictions[0]
        if isinstance(first, dict):
            for key in ("text", "transcript", "output"):
                value = first.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

    raise ValueError(f"Unable to extract transcript from ASR response: {json.dumps(payload)[:400]}")


def transcribe_bytes(
    file_bytes: bytes,
    filename: str = "audio.webm",
    content_type: str = "audio/webm",
    language: str = ASR_LANGUAGE,
) -> str:
    """Transcribe in-memory audio bytes using Higgs ASR."""
    payload = generate_file(
        model=HIGGS_ASR_MODEL,
        file_bytes=file_bytes,
        filename=filename,
        content_type=content_type,
        language=language,
    )
    return _extract_text(payload)


def transcribe_file(path: str, language: str = ASR_LANGUAGE) -> str:
    """Convenience: transcribe directly from an audio file path."""
    file_path = Path(path)
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    with open(file_path, "rb") as handle:
        return transcribe_bytes(
            handle.read(),
            filename=file_path.name,
            content_type=content_type,
            language=language,
        )


def transcribe(chunks: list[str], language: str = ASR_LANGUAGE) -> str:
    """Compatibility wrapper for base64-encoded audio chunks.

    Each chunk is a complete WAV with its own RIFF header, so they must
    be transcribed individually and the text joined afterwards.
    """
    parts: list[str] = []
    for i, chunk in enumerate(chunks):
        try:
            file_bytes = base64.b64decode(chunk)
        except Exception as exc:
            raise ValueError("Invalid base64 audio payload.") from exc
        text = transcribe_bytes(
            file_bytes,
            filename=f"chunk_{i}.wav",
            content_type="audio/wav",
            language=language,
        )
        if text and text.strip():
            parts.append(text.strip())
    return " ".join(parts)
