"""Coverage for API session backend selection."""

from __future__ import annotations

import importlib

import pytest

import api.app as api_app
import config.models as config_models


@pytest.fixture(autouse=True)
def _reset_backend_selector_state(monkeypatch: pytest.MonkeyPatch):
    original_service = api_app._SERVICE
    for key in (
        "SESSION_STORE_BACKEND",
        "SESSION_DB_PATH",
        "SESSION_TTL_SECONDS",
        "AEROSPIKE_HOSTS",
        "AEROSPIKE_NAMESPACE",
        "AEROSPIKE_SET",
    ):
        monkeypatch.delenv(key, raising=False)
    importlib.reload(config_models)
    api_app._SERVICE = None
    yield
    api_app._SERVICE = original_service
    importlib.reload(config_models)


class TestSessionBackendSelector:
    def test_build_session_store_uses_memory_backend(self, monkeypatch):
        monkeypatch.setenv("SESSION_STORE_BACKEND", "memory")
        monkeypatch.setenv("SESSION_TTL_SECONDS", "120")
        importlib.reload(config_models)

        calls = {}

        def _fake_memory_store(*, ttl_seconds):
            calls["memory"] = ttl_seconds
            return {"backend": "memory", "ttl_seconds": ttl_seconds}

        monkeypatch.setattr(api_app, "InMemorySessionStore", _fake_memory_store)

        store = api_app.build_session_store()

        assert store == {"backend": "memory", "ttl_seconds": 120}
        assert calls["memory"] == 120

    def test_build_session_store_uses_sqlite_backend(self, monkeypatch):
        monkeypatch.setenv("SESSION_STORE_BACKEND", "sqlite")
        monkeypatch.setenv("SESSION_DB_PATH", "data/sessions.sqlite3")
        monkeypatch.setenv("SESSION_TTL_SECONDS", "600")
        importlib.reload(config_models)

        calls = {}

        def _fake_sqlite_store(path, *, ttl_seconds):
            calls["sqlite"] = {"path": path, "ttl_seconds": ttl_seconds}
            return {"backend": "sqlite", "path": path, "ttl_seconds": ttl_seconds}

        monkeypatch.setattr(api_app, "SQLiteSessionStore", _fake_sqlite_store)

        store = api_app.build_session_store()

        assert store == {
            "backend": "sqlite",
            "path": "data/sessions.sqlite3",
            "ttl_seconds": 600,
        }
        assert calls["sqlite"] == {"path": "data/sessions.sqlite3", "ttl_seconds": 600}

    def test_build_session_store_uses_aerospike_backend(self, monkeypatch):
        monkeypatch.setenv("SESSION_STORE_BACKEND", "aerospike")
        monkeypatch.setenv("SESSION_TTL_SECONDS", "900")
        monkeypatch.setenv("AEROSPIKE_HOSTS", "10.0.0.1:3000,10.0.0.2:3001")
        monkeypatch.setenv("AEROSPIKE_NAMESPACE", "hackathon")
        monkeypatch.setenv("AEROSPIKE_SET", "call_sessions")
        importlib.reload(config_models)

        calls = {}

        def _fake_aerospike_store(*, hosts, namespace, set_name, ttl_seconds):
            calls["aerospike"] = {
                "hosts": hosts,
                "namespace": namespace,
                "set_name": set_name,
                "ttl_seconds": ttl_seconds,
            }
            return {"backend": "aerospike", **calls["aerospike"]}

        monkeypatch.setattr(api_app, "AerospikeSessionStore", _fake_aerospike_store)

        store = api_app.build_session_store()

        assert store == {
            "backend": "aerospike",
            "hosts": "10.0.0.1:3000,10.0.0.2:3001",
            "namespace": "hackathon",
            "set_name": "call_sessions",
            "ttl_seconds": 900,
        }

    def test_build_session_store_rejects_unknown_backend(self, monkeypatch):
        monkeypatch.setenv("SESSION_STORE_BACKEND", "redis")
        importlib.reload(config_models)

        with pytest.raises(ValueError) as excinfo:
            api_app.build_session_store()

        assert "SESSION_STORE_BACKEND" in str(excinfo.value)

    def test_get_service_uses_selected_store_builder_once(self, monkeypatch):
        monkeypatch.setenv("SESSION_STORE_BACKEND", "memory")
        importlib.reload(config_models)

        built_stores = []

        def _fake_build_session_store():
            built_stores.append("built")
            return object()

        monkeypatch.setattr(api_app, "build_session_store", _fake_build_session_store)

        first = api_app.get_service()
        second = api_app.get_service()

        assert first is second
        assert built_stores == ["built"]
