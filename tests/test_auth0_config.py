"""DEV-62 coverage for Auth0 config constants."""

from __future__ import annotations

import importlib

import config.models as config


class TestAuth0Config:
    def test_auth0_constants_are_exposed_from_config(self):
        assert hasattr(config, "AUTH_ENABLED")
        assert isinstance(config.AUTH_ENABLED, bool)

        assert hasattr(config, "AUTH0_DOMAIN")
        assert isinstance(config.AUTH0_DOMAIN, str)

        assert hasattr(config, "AUTH0_AUDIENCE")
        assert isinstance(config.AUTH0_AUDIENCE, str)

    def test_auth_enabled_truthy_values_are_true(self, monkeypatch):
        for value in ("true", "1", "yes"):
            monkeypatch.setenv("AUTH_ENABLED", value)
            importlib.reload(config)
            assert config.AUTH_ENABLED is True

    def test_auth_enabled_non_truthy_values_are_false(self, monkeypatch):
        for value in ("false", "0", "no", ""):
            monkeypatch.setenv("AUTH_ENABLED", value)
            importlib.reload(config)
            assert config.AUTH_ENABLED is False

        monkeypatch.delenv("AUTH_ENABLED", raising=False)
        importlib.reload(config)
        assert config.AUTH_ENABLED is False

    def test_auth0_domain_and_audience_reflect_raw_env_values(self, monkeypatch):
        monkeypatch.setenv("AUTH0_DOMAIN", "tenant.us.auth0.com")
        monkeypatch.setenv("AUTH0_AUDIENCE", "https://api.example.com")
        importlib.reload(config)

        assert config.AUTH0_DOMAIN == "tenant.us.auth0.com"
        assert config.AUTH0_AUDIENCE == "https://api.example.com"
