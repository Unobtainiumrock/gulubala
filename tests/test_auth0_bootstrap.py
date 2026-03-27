"""Coverage for Auth0 dependency and env bootstrap."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestAuth0Bootstrap:
    def test_env_example_lists_auth0_variables(self):
        env_lines = (REPO_ROOT / ".env.example").read_text().splitlines()

        for key in (
            "AUTH_ENABLED",
            "AUTH0_DOMAIN",
            "AUTH0_AUDIENCE",
        ):
            assert any(line.startswith(f"{key}=") for line in env_lines)

        assert any(line == "AUTH_ENABLED=false" for line in env_lines)

    def test_requirements_include_python_jose_crypto_dependency(self):
        requirements = (REPO_ROOT / "requirements.txt").read_text().splitlines()

        assert any(line.startswith("python-jose[cryptography]") for line in requirements)
