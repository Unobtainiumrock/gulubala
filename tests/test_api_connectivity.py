"""Live API connectivity smoke tests.

Skipped when EIGEN_API_KEY is not set so CI runs without credentials.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_has_key = bool(os.environ.get("EIGEN_API_KEY"))
pytestmark = pytest.mark.skipif(not _has_key, reason="EIGEN_API_KEY not set")


@pytest.fixture(scope="module")
def eigen_client():
    from client.eigen import get_client
    return get_client()


class TestApiConnectivity:
    """Verify we can reach the Eigen API and that expected models exist."""

    def test_list_models_includes_gpt_oss(self):
        """Use raw requests since the Eigen /models response may not match
        the OpenAI pagination format exactly."""
        import requests
        from client.eigen import _get_api_key, _get_base_url

        url = f"{_get_base_url()}/models"
        headers = {"Authorization": f"Bearer {_get_api_key()}"}
        resp = requests.get(url, headers=headers, timeout=30)
        assert resp.status_code == 200, f"GET /models returned {resp.status_code}"
        body = resp.json()
        if isinstance(body, list):
            model_ids = [m.get("id") or m for m in body]
        elif isinstance(body, dict) and "data" in body:
            model_ids = [m.get("id") or m for m in body["data"]]
        else:
            model_ids = [str(body)]
        assert any("gpt-oss" in str(mid) for mid in model_ids), (
            f"gpt-oss model not found in: {model_ids[:20]}"
        )

    def test_chat_completion_returns_text(self):
        """Verify a basic chat completion round-trip succeeds."""
        from client.eigen import chat_completion
        from config.models import GPT_OSS_MODEL

        result = chat_completion(
            model=GPT_OSS_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What is 2 + 2? Answer with just the number."},
            ],
            temperature=0.0,
            max_tokens=32,
        )
        assert result is not None, "chat_completion returned None"
        assert isinstance(result, str)

    def test_intent_classification_returns_valid_json(self):
        from intents.router import classify_intent

        result = classify_intent("I need to reset my password")
        assert "intent" in result
        assert "confidence" in result
        assert isinstance(result["confidence"], float)
        assert result["intent"] in (
            "password_reset",
            "unsupported",
        )
