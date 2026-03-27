"""Coverage for Auth0 JWT middleware dependency."""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import importlib
from typing import Any

import pytest

pytest.importorskip("cryptography")
pytest.importorskip("jose")

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jose import jwt

import auth.middleware as auth_middleware
import config.models as config_models


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _build_token_fixture(
    *,
    audience: str,
    issuer: str,
    kid: str = "test-key",
    expires_in_seconds: int = 3600,
) -> tuple[str, dict[str, Any]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_numbers = private_key.public_key().public_numbers()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    now = datetime.now(tz=timezone.utc)
    token = jwt.encode(
        {
            "sub": "user_123",
            "aud": audience,
            "iss": issuer,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=expires_in_seconds)).timestamp()),
        },
        private_pem,
        algorithm="RS256",
        headers={"kid": kid, "typ": "JWT"},
    )

    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "kid": kid,
                "use": "sig",
                "alg": "RS256",
                "n": _b64url_uint(public_numbers.n),
                "e": _b64url_uint(public_numbers.e),
            }
        ]
    }
    return token, jwks


def _build_client() -> TestClient:
    app = FastAPI()

    @app.get("/protected")
    async def protected(
        claims: dict[str, Any] | None = Depends(auth_middleware.verify_jwt),
    ):
        return {"claims": claims}

    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_auth_state(monkeypatch: pytest.MonkeyPatch):
    auth_middleware.clear_jwks_cache()
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    monkeypatch.delenv("AUTH0_DOMAIN", raising=False)
    monkeypatch.delenv("AUTH0_AUDIENCE", raising=False)
    importlib.reload(config_models)
    yield
    auth_middleware.clear_jwks_cache()
    importlib.reload(config_models)


class TestAuthMiddleware:
    def test_verify_jwt_is_noop_when_auth_disabled(self):
        client = _build_client()

        response = client.get("/protected")

        assert response.status_code == 200
        assert response.json() == {"claims": None}

    def test_verify_jwt_rejects_missing_bearer_token_when_enabled(self, monkeypatch):
        monkeypatch.setenv("AUTH_ENABLED", "true")
        monkeypatch.setenv("AUTH0_DOMAIN", "tenant.us.auth0.com")
        monkeypatch.setenv("AUTH0_AUDIENCE", "https://api.example.com")
        importlib.reload(config_models)

        client = _build_client()
        response = client.get("/protected")

        assert response.status_code == 401
        assert response.json()["detail"] == "Missing or invalid bearer token."

    def test_verify_jwt_returns_claims_for_valid_token_and_uses_jwks_cache(
        self,
        monkeypatch,
    ):
        monkeypatch.setenv("AUTH_ENABLED", "true")
        monkeypatch.setenv("AUTH0_DOMAIN", "tenant.us.auth0.com")
        monkeypatch.setenv("AUTH0_AUDIENCE", "https://api.example.com")
        importlib.reload(config_models)

        token, jwks = _build_token_fixture(
            audience="https://api.example.com",
            issuer="https://tenant.us.auth0.com/",
        )
        calls = {"count": 0}

        def _fake_download(_url: str) -> dict[str, Any]:
            calls["count"] += 1
            return jwks

        monkeypatch.setattr(auth_middleware, "_download_jwks", _fake_download)
        client = _build_client()
        headers = {"Authorization": f"Bearer {token}"}

        first = client.get("/protected", headers=headers)
        second = client.get("/protected", headers=headers)

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["claims"]["sub"] == "user_123"
        assert calls["count"] == 1

    def test_verify_jwt_rejects_invalid_audience(self, monkeypatch):
        monkeypatch.setenv("AUTH_ENABLED", "true")
        monkeypatch.setenv("AUTH0_DOMAIN", "tenant.us.auth0.com")
        monkeypatch.setenv("AUTH0_AUDIENCE", "https://api.example.com")
        importlib.reload(config_models)

        token, jwks = _build_token_fixture(
            audience="https://different.example.com",
            issuer="https://tenant.us.auth0.com/",
        )
        monkeypatch.setattr(auth_middleware, "_download_jwks", lambda _url: jwks)
        client = _build_client()

        response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})

        assert response.status_code == 401
        assert response.json()["detail"] == "JWT audience does not match Auth0 config."

    def test_verify_jwt_requires_domain_and_audience_when_enabled(self, monkeypatch):
        monkeypatch.setenv("AUTH_ENABLED", "true")
        importlib.reload(config_models)

        client = _build_client()
        response = client.get("/protected", headers={"Authorization": "Bearer token"})

        assert response.status_code == 503
        assert "AUTH0_DOMAIN or AUTH0_AUDIENCE" in response.json()["detail"]
