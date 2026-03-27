"""Coverage for Aerospike dependency and env bootstrap."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestAerospikeBootstrap:
    def test_env_example_lists_required_aerospike_variables(self):
        env_lines = (REPO_ROOT / ".env.example").read_text().splitlines()

        for key in (
            "SESSION_STORE_BACKEND",
            "SESSION_DB_PATH",
            "SESSION_TTL_SECONDS",
            "AEROSPIKE_HOSTS",
            "AEROSPIKE_NAMESPACE",
            "AEROSPIKE_SET",
        ):
            assert any(line.startswith(f"{key}=") for line in env_lines)

    def test_requirements_include_aerospike_runtime_dependency(self):
        requirements = (REPO_ROOT / "requirements.txt").read_text().splitlines()

        assert any(line.startswith("aerospike") for line in requirements)
