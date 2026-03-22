"""Demo scripted IVR lines."""

from __future__ import annotations

import pytest

from calltree.demo_ivr_scripts import DEMO_IVR_SCRIPTS, get_demo_ivr_script


def test_cancel_service_script_nonempty() -> None:
    lines = get_demo_ivr_script("cancel_service")
    assert len(lines) >= 5
    assert all(isinstance(d, float) and d > 0 for d, _ in lines)
    assert any("cancel" in t.lower() for _, t in lines)


def test_password_reset_script_nonempty() -> None:
    lines = get_demo_ivr_script("password_reset")
    assert len(lines) >= 3


def test_unknown_scenario_raises() -> None:
    with pytest.raises(KeyError):
        get_demo_ivr_script("not_a_scenario")


def test_demo_keys_match_main_defaults() -> None:
    assert {"cancel_service", "password_reset"} <= DEMO_IVR_SCRIPTS.keys()
