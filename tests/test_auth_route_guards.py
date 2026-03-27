"""Coverage for Auth0-protected API routes."""

from __future__ import annotations

import importlib

from fastapi.testclient import TestClient
import pytest

import api.app as api_app
import auth.middleware as auth_middleware
import config.models as config_models
from calltree.transcript_store import clear_transcript, record_transcript_turn
from tests.conftest import make_service


def _enable_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH0_DOMAIN", "tenant.us.auth0.com")
    monkeypatch.setenv("AUTH0_AUDIENCE", "https://api.example.com")
    importlib.reload(config_models)


@pytest.fixture(autouse=True)
def _reset_auth_route_state(monkeypatch: pytest.MonkeyPatch):
    original_service = api_app._SERVICE
    auth_middleware.clear_jwks_cache()
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    monkeypatch.delenv("AUTH0_DOMAIN", raising=False)
    monkeypatch.delenv("AUTH0_AUDIENCE", raising=False)
    importlib.reload(config_models)
    yield
    api_app._SERVICE = original_service
    auth_middleware.clear_jwks_cache()
    importlib.reload(config_models)


class TestAuthRouteGuards:
    def test_health_route_stays_public_when_auth_enabled(self, monkeypatch):
        _enable_auth(monkeypatch)

        client = TestClient(api_app.create_app())

        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_demo_routes_stay_public_when_auth_enabled(self, monkeypatch):
        _enable_auth(monkeypatch)
        api_app._SERVICE = make_service(monkeypatch, "password_reset")

        client = TestClient(api_app.create_app())
        response = client.get("/demo/scenarios")

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_bland_routes_stay_public_when_auth_enabled(self, monkeypatch):
        _enable_auth(monkeypatch)
        api_app._SERVICE = make_service(monkeypatch, "password_reset")

        client = TestClient(api_app.create_app())
        response = client.post(
            "/bland/tool/start-session",
            json={"call_id": "bland-public-1"},
        )

        assert response.status_code == 200
        assert response.json()["session_id"] == "bland-public-1"

    def test_ivr_routes_stay_public_when_auth_enabled(self, monkeypatch):
        _enable_auth(monkeypatch)

        client = TestClient(api_app.create_app())
        response = client.post(
            "/ivr/status-callback",
            data={"CallSid": "CA123", "CallStatus": "completed"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/xml")

    def test_transcript_route_stays_public_when_auth_enabled(self, monkeypatch):
        _enable_auth(monkeypatch)
        client = TestClient(api_app.create_app())
        session_id = "guarded-transcript"
        clear_transcript(session_id)
        record_transcript_turn(session_id, "ivr", "Press 1 for billing")

        try:
            response = client.get(f"/transcript/{session_id}")
        finally:
            clear_transcript(session_id)

        assert response.status_code == 200
        assert response.json()["session_id"] == session_id

    def test_escalation_summary_stays_public_when_auth_enabled(self, monkeypatch):
        _enable_auth(monkeypatch)
        service = make_service(monkeypatch, "password_reset")
        service.create_session(channel="api", session_id="summary-session")
        api_app._SERVICE = service

        client = TestClient(api_app.create_app())
        response = client.post(
            "/escalation-summary",
            json={"session_id": "summary-session"},
        )

        assert response.status_code == 200
        assert response.json()["session_id"] == "summary-session"

    def test_route_intent_requires_bearer_token_when_auth_enabled(self, monkeypatch):
        _enable_auth(monkeypatch)
        api_app._SERVICE = make_service(monkeypatch, "password_reset")

        client = TestClient(api_app.create_app())
        response = client.post(
            "/route-intent",
            json={"session_id": "guarded-session", "utterance": "I cannot log in."},
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "Missing or invalid bearer token."

    def test_submit_document_requires_bearer_token_when_auth_enabled(self, monkeypatch):
        _enable_auth(monkeypatch)
        api_app._SERVICE = make_service(monkeypatch, "billing_dispute")

        client = TestClient(api_app.create_app())
        response = client.post(
            "/submit-document",
            json={"session_id": "guarded-session", "document_text": "reference: ABC123"},
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "Missing or invalid bearer token."

    def test_protected_route_allows_requests_with_dependency_override(self, monkeypatch):
        _enable_auth(monkeypatch)
        api_app._SERVICE = make_service(monkeypatch, "password_reset")

        app = api_app.create_app()
        app.dependency_overrides[auth_middleware.verify_jwt] = lambda: {"sub": "user_123"}
        client = TestClient(app)

        response = client.post(
            "/route-intent",
            json={"session_id": "guarded-session", "utterance": "I cannot log in."},
        )

        assert response.status_code == 200
        assert response.json()["intent"] == "password_reset"
