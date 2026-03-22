"""Live API connectivity smoke tests.

These tests are intentionally opt-in because they require real credentials and
outbound network access. Run them with:

``RUN_LIVE_EIGEN_TESTS=1 pytest tests/test_api_connectivity.py``

Optional rate-limit probe (bursts unthrottled HTTP POSTs; may see 429):

``RUN_LIVE_EIGEN_TESTS=1 EIGEN_RATE_LIMIT_PROBE=1 pytest tests/test_api_connectivity.py -k rate_limit``
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
_run_live = os.environ.get("RUN_LIVE_EIGEN_TESTS") == "1"
_rate_probe = os.environ.get("EIGEN_RATE_LIMIT_PROBE") == "1"
pytestmark = pytest.mark.skipif(
    not (_has_key and _run_live),
    reason="live Eigen connectivity tests require EIGEN_API_KEY and RUN_LIVE_EIGEN_TESTS=1",
)


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


@pytest.mark.skipif(
    not (_has_key and _run_live and _rate_probe),
    reason="set EIGEN_RATE_LIMIT_PROBE=1 with RUN_LIVE_EIGEN_TESTS=1 and EIGEN_API_KEY",
)
def test_eigen_chat_burst_reports_status_codes_for_rate_limit_diagnosis():
    """Fire several chat completions without ``client.eigen.chat_completion``'s 2s throttle.

    HTTP **429** means the server rejected the request as too many (RFC 6585). If you see
    only **200** here, your account tolerated this burst; that does not prove you have no limits.

    Uses raw httpx so behavior is independent of the OpenAI SDK wrapper.
    """
    import httpx

    from client.eigen import _get_api_key, _get_base_url
    from config.models import EXTRA_BODY, GPT_OSS_MODEL, STOP_SEQUENCES

    url = f"{_get_base_url()}/chat/completions"
    headers = {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": GPT_OSS_MODEL,
        "messages": [{"role": "user", "content": "Reply with only: ok"}],
        "max_tokens": 8,
        "temperature": 0.0,
        "stop": STOP_SEQUENCES,
        **EXTRA_BODY,
    }
    codes: list[int] = []
    with httpx.Client(timeout=60.0) as client:
        for _ in range(12):
            r = client.post(url, headers=headers, json=payload)
            codes.append(r.status_code)
            if r.status_code == 429:
                break

    assert codes, "expected at least one HTTP response"
    assert all(c in (200, 429) for c in codes), f"unexpected status codes: {codes}"
    assert codes[0] == 200, f"first request should succeed; got {codes[0]}: {codes}"
    # If we never saw 429, the probe still passes — limits may be higher than this burst.
