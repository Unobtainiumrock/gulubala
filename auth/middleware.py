"""Auth0 JWT verification helpers for FastAPI dependencies."""

from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any

import httpx
from fastapi import HTTPException, Request, status

import config.models as config_models


_JWKS_CACHE_TTL_SECONDS = 300
_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def clear_jwks_cache() -> None:
    """Clear the in-memory JWKS cache."""

    _JWKS_CACHE.clear()


def get_jwks(*, force_refresh: bool = False) -> dict[str, Any]:
    """Return the Auth0 JWKS payload, using a small in-memory cache."""

    jwks_url = _jwks_url()
    now = time.time()
    cached = _JWKS_CACHE.get(jwks_url)
    if cached is not None and not force_refresh and cached[0] > now:
        return cached[1]

    payload = _download_jwks(jwks_url)
    _JWKS_CACHE[jwks_url] = (now + _JWKS_CACHE_TTL_SECONDS, payload)
    return payload


async def verify_jwt(request: Request) -> dict[str, Any] | None:
    """Verify an incoming bearer token when Auth0 protection is enabled."""

    if not config_models.AUTH_ENABLED:
        return None

    if not config_models.AUTH0_DOMAIN or not config_models.AUTH0_AUDIENCE:
        raise _http_exception(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Auth0 is enabled but AUTH0_DOMAIN or AUTH0_AUDIENCE is not configured.",
        )

    token = _extract_bearer_token(request)
    signing_key = _resolve_signing_key(token)
    claims = _validate_token(token, signing_key)
    request.state.auth_claims = claims
    return claims


def _download_jwks(jwks_url: str) -> dict[str, Any]:
    """Fetch the JSON Web Key Set from Auth0."""

    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(jwks_url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise _http_exception(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"Unable to fetch Auth0 JWKS: {exc}",
        ) from exc

    payload = response.json()
    keys = payload.get("keys")
    if not isinstance(keys, list):
        raise _http_exception(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Auth0 JWKS response did not contain a valid 'keys' list.",
        )
    return payload


def _extract_bearer_token(request: Request) -> str:
    authorization = request.headers.get("Authorization", "").strip()
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _http_exception(
            status.HTTP_401_UNAUTHORIZED,
            "Missing or invalid bearer token.",
        )
    return token


def _resolve_signing_key(token: str) -> dict[str, Any]:
    from jose import jwt

    try:
        header = jwt.get_unverified_header(token)
    except Exception as exc:  # pragma: no cover - library exceptions vary by version
        raise _http_exception(
            status.HTTP_401_UNAUTHORIZED,
            f"Invalid JWT header: {exc}",
        ) from exc

    if header.get("alg") != "RS256":
        raise _http_exception(
            status.HTTP_401_UNAUTHORIZED,
            "Unsupported JWT signing algorithm.",
        )

    kid = header.get("kid")
    if not kid:
        raise _http_exception(
            status.HTTP_401_UNAUTHORIZED,
            "JWT header is missing 'kid'.",
        )

    keys = get_jwks().get("keys", [])
    for key in keys:
        if key.get("kid") == kid:
            return key
    raise _http_exception(
        status.HTTP_401_UNAUTHORIZED,
        "Unable to find a matching JWKS key.",
    )


def _validate_token(token: str, signing_key: dict[str, Any]) -> dict[str, Any]:
    from jose import jwk, jwt
    from jose.utils import base64url_decode

    key = jwk.construct(signing_key)

    try:
        message, encoded_signature = token.rsplit(".", 1)
    except ValueError as exc:
        raise _http_exception(status.HTTP_401_UNAUTHORIZED, "Malformed JWT.") from exc

    decoded_signature = base64url_decode(encoded_signature.encode("utf-8"))
    if not key.verify(message.encode("utf-8"), decoded_signature):
        raise _http_exception(
            status.HTTP_401_UNAUTHORIZED,
            "JWT signature verification failed.",
        )

    try:
        claims = jwt.get_unverified_claims(token)
    except Exception as exc:  # pragma: no cover - library exceptions vary by version
        raise _http_exception(
            status.HTTP_401_UNAUTHORIZED,
            f"Invalid JWT claims: {exc}",
        ) from exc

    _validate_claims(claims)
    return claims


def _validate_claims(claims: dict[str, Any]) -> None:
    now = int(datetime.now(tz=timezone.utc).timestamp())

    exp = claims.get("exp")
    if not isinstance(exp, (int, float)):
        raise _http_exception(
            status.HTTP_401_UNAUTHORIZED,
            "JWT is missing a valid expiration claim.",
        )
    if int(exp) <= now:
        raise _http_exception(status.HTTP_401_UNAUTHORIZED, "JWT has expired.")

    nbf = claims.get("nbf")
    if isinstance(nbf, (int, float)) and int(nbf) > now:
        raise _http_exception(status.HTTP_401_UNAUTHORIZED, "JWT is not valid yet.")

    issuer = claims.get("iss")
    if issuer != _auth0_issuer():
        raise _http_exception(
            status.HTTP_401_UNAUTHORIZED,
            "JWT issuer does not match Auth0 config.",
        )

    audience = claims.get("aud")
    configured_audience = config_models.AUTH0_AUDIENCE
    if isinstance(audience, str):
        valid_audience = audience == configured_audience
    elif isinstance(audience, list):
        valid_audience = configured_audience in audience
    else:
        valid_audience = False
    if not valid_audience:
        raise _http_exception(
            status.HTTP_401_UNAUTHORIZED,
            "JWT audience does not match Auth0 config.",
        )


def _normalized_auth0_base_url() -> str:
    domain = config_models.AUTH0_DOMAIN.strip().rstrip("/")
    if domain.startswith("http://") or domain.startswith("https://"):
        return domain
    return f"https://{domain}"


def _auth0_issuer() -> str:
    return f"{_normalized_auth0_base_url().rstrip('/')}/"


def _jwks_url() -> str:
    return f"{_normalized_auth0_base_url().rstrip('/')}/.well-known/jwks.json"


def _http_exception(status_code: int, detail: str) -> HTTPException:
    headers = (
        {"WWW-Authenticate": "Bearer"}
        if status_code == status.HTTP_401_UNAUTHORIZED
        else None
    )
    return HTTPException(status_code=status_code, detail=detail, headers=headers)
