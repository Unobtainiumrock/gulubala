"""Eigen AI client wrappers for chat and generate endpoints."""

import os
import threading
import time

from dotenv import load_dotenv
from config.models import (
    EIGEN_BASE_URL,
    EIGEN_GENERATE_URL,
    EIGEN_UPLOAD_URL,
    EXTRA_BODY,
    HIGGS_TTS_MODEL,
    STOP_SEQUENCES,
)

load_dotenv()

_client = None

# Simple throttle to avoid Eigen 429 rate limits.
_throttle_lock = threading.Lock()
_MIN_INTERVAL = 2.0  # seconds between requests
_last_request_time = 0.0


def _get_api_key() -> str:
    """Return the configured Eigen API key or fail with a clear error."""
    try:
        return os.environ["EIGEN_API_KEY"]
    except KeyError as exc:  # pragma: no cover - exercised in misconfigured envs
        raise KeyError("EIGEN_API_KEY is not set") from exc


def _get_base_url() -> str:
    """Return the configured Eigen-compatible API base URL."""
    return EIGEN_BASE_URL.rstrip("/")


def get_client():
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
    global _last_request_time
    with _throttle_lock:
        now = time.monotonic()
        wait = _MIN_INTERVAL - (now - _last_request_time)
        if wait > 0:
            time.sleep(wait)
        _last_request_time = time.monotonic()

    client = get_client()
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        stop=STOP_SEQUENCES,
        extra_body=EXTRA_BODY,
        **kwargs,
    )
    return response.choices[0].message.content


def generate_file(model: str, file_bytes: bytes, filename: str, content_type: str, **form_fields):
    """Send a multipart file request to the Eigen generate endpoint."""
    import httpx

    api_key = _get_api_key()
    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            EIGEN_GENERATE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            data={"model": model, **form_fields},
            files={
                "file": (
                    filename,
                    file_bytes,
                    content_type or "application/octet-stream",
                )
            },
        )
        response.raise_for_status()
        return response.json()


def upload_voice_reference(audio_file_path: str) -> str:
    """Upload a voice reference file and return a persistent voice_id.

    The file (WAV or MP3) is sent to Eigen's upload endpoint.
    Returns the ``voice_id`` string for use in subsequent TTS calls.
    """
    import mimetypes
    import httpx

    mime, _ = mimetypes.guess_type(audio_file_path)
    if mime is None:
        mime = "audio/wav"

    api_key = _get_api_key()
    with open(audio_file_path, "rb") as f:
        file_bytes = f.read()

    with httpx.Client(timeout=120.0) as client:
        response = client.post(
            EIGEN_UPLOAD_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            data={"model": HIGGS_TTS_MODEL},
            files={"voice_reference_file": (os.path.basename(audio_file_path), file_bytes, mime)},
        )
        response.raise_for_status()
        data = response.json()
    voice_id = data.get("voice_id") or data.get("id")
    if not voice_id:
        raise ValueError(f"Eigen upload response did not contain a voice_id: {data}")
    return voice_id


def generate_form(model: str, expect_json: bool = True, **form_fields):
    """Send a non-file form request to the Eigen generate endpoint."""
    import httpx

    api_key = _get_api_key()
    multipart_fields = [("model", (None, str(model)))]
    for key, value in form_fields.items():
        multipart_fields.append((key, (None, str(value))))

    with httpx.Client(timeout=60.0) as client:
        response = client.post(
            EIGEN_GENERATE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            files=multipart_fields,
        )
        response.raise_for_status()
        if expect_json:
            return response.json()
        return response.content
