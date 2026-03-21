"""Eigen AI client wrapper using OpenAI-compatible API."""

import os

from dotenv import load_dotenv
from config.models import STOP_SEQUENCES, EXTRA_BODY

load_dotenv()

_client = None


def get_client():
    """Return a shared OpenAI client configured for Eigen AI."""
    global _client
    if _client is None:
        from openai import OpenAI

        _client = OpenAI(
            api_key=os.environ["EIGEN_API_KEY"],
            base_url=os.environ.get("EIGEN_BASE_URL", "https://app.eigenai.com/v1"),
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
