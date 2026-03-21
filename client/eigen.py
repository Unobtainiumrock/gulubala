"""Eigen AI client wrapper using OpenAI-compatible API."""

from __future__ import annotations

import base64
import io
import os
from typing import TYPE_CHECKING

import requests
from dotenv import load_dotenv

from config.models import HIGGS_ASR_MODEL, STOP_SEQUENCES, EXTRA_BODY

if TYPE_CHECKING:
    from openai import OpenAI

load_dotenv()

DEFAULT_BASE_URL = "https://api-web.eigenai.com/api/v1"

_client: OpenAI | None = None


def _get_base_url() -> str:
    return os.environ.get("EIGEN_BASE_URL", DEFAULT_BASE_URL)


def _get_api_key() -> str:
    return os.environ["EIGEN_API_KEY"]


def get_client() -> OpenAI:
    """Return a shared OpenAI client configured for Eigen AI."""
    global _client
    if _client is None:
        from openai import OpenAI

        _client = OpenAI(
            api_key=_get_api_key(),
            base_url=_get_base_url(),
        )
    return _client


def chat_completion(model: str, messages: list, **kwargs) -> str:
    """Send a chat completion request with standard Eigen parameters.

    Returns the assistant's response text.
    """
    client = get_client()
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        stop=STOP_SEQUENCES,
        extra_body=EXTRA_BODY,
        **kwargs,
    )
    return response.choices[0].message.content


def asr_generate(
    audio_bytes: bytes,
    *,
    model: str = HIGGS_ASR_MODEL,
    language: str = "English",
    filename: str = "chunk.wav",
) -> str:
    """Transcribe audio via the Eigen ASR multipart /generate endpoint.

    Args:
        audio_bytes: Raw WAV binary data.
        model: ASR model identifier.
        language: Transcription language.
        filename: Filename hint for the upload.

    Returns:
        Transcribed text.
    """
    base_url = _get_base_url()
    url = f"{base_url}/generate"
    headers = {"Authorization": f"Bearer {_get_api_key()}"}
    files = {"file": (filename, io.BytesIO(audio_bytes), "audio/wav")}
    data = {"model": model, "language": language}

    resp = requests.post(url, headers=headers, files=files, data=data, timeout=60)
    resp.raise_for_status()

    body = resp.json()
    if isinstance(body, dict):
        return body.get("text", body.get("output", str(body)))
    return str(body)


def decode_b64_audio(b64_chunk: str) -> bytes:
    """Decode a base64-encoded WAV string to raw bytes."""
    return base64.b64decode(b64_chunk)
