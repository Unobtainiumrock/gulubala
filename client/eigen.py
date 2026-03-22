"""Eigen AI client wrappers for chat and generate endpoints."""

import os

from dotenv import load_dotenv
from config.models import EIGEN_BASE_URL, EIGEN_GENERATE_URL, EXTRA_BODY, STOP_SEQUENCES

load_dotenv()

_client = None


def get_client():
    """Return a shared OpenAI client configured for Eigen AI."""
    global _client
    if _client is None:
        from openai import OpenAI

        _client = OpenAI(
            api_key=os.environ["EIGEN_API_KEY"],
            base_url=EIGEN_BASE_URL,
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


def generate_file(model: str, file_bytes: bytes, filename: str, content_type: str, **form_fields):
    """Send a multipart file request to the Eigen generate endpoint."""
    import httpx

    api_key = os.environ["EIGEN_API_KEY"]
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


def generate_form(model: str, expect_json: bool = True, **form_fields):
    """Send a non-file form request to the Eigen generate endpoint."""
    import httpx

    api_key = os.environ["EIGEN_API_KEY"]
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
