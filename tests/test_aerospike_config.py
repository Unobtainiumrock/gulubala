"""Coverage for Aerospike session backend configuration."""

from __future__ import annotations

import importlib

import pytest

import config.models as config_models


@pytest.fixture(autouse=True)
def _reset_aerospike_env(monkeypatch: pytest.MonkeyPatch):
    for key in (
        "SESSION_STORE_BACKEND",
        "AEROSPIKE_HOSTS",
        "AEROSPIKE_NAMESPACE",
        "AEROSPIKE_SET",
    ):
        monkeypatch.delenv(key, raising=False)
    importlib.reload(config_models)
    yield
    importlib.reload(config_models)


class TestAerospikeConfig:
    def test_aerospike_constants_are_exposed_from_config(self):
        for name in (
            "SESSION_STORE_BACKEND",
            "AEROSPIKE_HOSTS",
            "AEROSPIKE_NAMESPACE",
            "AEROSPIKE_SET",
        ):
            assert hasattr(config_models, name)
            assert isinstance(getattr(config_models, name), str)

    def test_aerospike_defaults_match_current_local_runtime(self):
        assert config_models.SESSION_STORE_BACKEND == "sqlite"
        assert config_models.AEROSPIKE_HOSTS == "127.0.0.1:3000"
        assert config_models.AEROSPIKE_NAMESPACE == "test"
        assert config_models.AEROSPIKE_SET == "sessions"

    def test_aerospike_env_overrides_are_loaded(self, monkeypatch):
        monkeypatch.setenv("SESSION_STORE_BACKEND", " Aerospike ")
        monkeypatch.setenv("AEROSPIKE_HOSTS", "10.0.0.1:3000,10.0.0.2:3000")
        monkeypatch.setenv("AEROSPIKE_NAMESPACE", "hackathon")
        monkeypatch.setenv("AEROSPIKE_SET", "call_sessions")
        importlib.reload(config_models)

        assert config_models.SESSION_STORE_BACKEND == "aerospike"
        assert config_models.AEROSPIKE_HOSTS == "10.0.0.1:3000,10.0.0.2:3000"
        assert config_models.AEROSPIKE_NAMESPACE == "hackathon"
        assert config_models.AEROSPIKE_SET == "call_sessions"
