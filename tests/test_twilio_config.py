"""DEV-30 coverage for Twilio config, dependencies, and env example."""

from __future__ import annotations

from pathlib import Path

import config.models as config


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestTwilioConfig:
    def test_twilio_constants_are_exposed_from_config(self):
        for name in (
            "TWILIO_ACCOUNT_SID",
            "TWILIO_AUTH_TOKEN",
            "TWILIO_IVR_NUMBER",
            "TWILIO_AGENT_NUMBER",
            "PRESENTER_PHONE_NUMBER",
        ):
            assert hasattr(config, name)
            assert isinstance(getattr(config, name), str)

    def test_env_example_lists_required_twilio_variables(self):
        env_lines = (REPO_ROOT / ".env.example").read_text().splitlines()

        for key in (
            "TWILIO_ACCOUNT_SID",
            "TWILIO_AUTH_TOKEN",
            "TWILIO_IVR_NUMBER",
            "TWILIO_AGENT_NUMBER",
            "PRESENTER_PHONE_NUMBER",
        ):
            assert any(line.startswith(f"{key}=") for line in env_lines)

    def test_requirements_include_twilio_runtime_dependencies(self):
        requirements = (REPO_ROOT / "requirements.txt").read_text().splitlines()

        assert any(line.startswith("twilio>=9.0.0") for line in requirements)
        assert any(line.startswith("pipecat-ai[websocket,silero]") for line in requirements)
