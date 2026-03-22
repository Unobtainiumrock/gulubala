"""Call-tree, IVR bridge, and TwiML route coverage."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import api.app as app_mod
from calltree.models import CallTreeSchema
from calltree.registry import get_call_tree, get_call_tree_node
from ivr.agent import cleanup_call, process_agent_turn, start_agent_session
from ivr.state import get_call_state
from tests.conftest import make_service
from workflows.registry import list_intents


def _make_client(monkeypatch: pytest.MonkeyPatch, intent: str = "password_reset") -> TestClient:
    service = make_service(monkeypatch, intent)
    app_mod._SERVICE = service
    return TestClient(app_mod.create_app())


class TestCallTreeSchema:
    """DEV-31 coverage for call-tree loading and validation."""

    def test_loads_acme_corp_root_node(self):
        tree = get_call_tree()
        assert tree is not None
        assert tree.id == "acme_corp"
        assert tree.root_node_id == "root"

        root = get_call_tree_node("acme_corp", "root")
        assert root is not None
        assert root.label == "Main Menu"
        assert any(item.input == "1" and item.next_node_id == "billing_menu" for item in root.transitions)

    def test_rejects_duplicate_node_ids(self):
        with pytest.raises(ValidationError, match="duplicate node ids"):
            CallTreeSchema.model_validate(
                {
                    "id": "bad_tree",
                    "brand": "Acme Corp",
                    "root_node_id": "root",
                    "nodes": [
                        {
                            "id": "root",
                            "label": "Root",
                            "prompt": "Press 1.",
                            "input_type": "dtmf",
                            "transitions": [{"input": "1", "next_node_id": "root"}],
                        },
                        {
                            "id": "root",
                            "label": "Duplicate",
                            "prompt": "Duplicate root.",
                            "input_type": "speech",
                            "intent": "password_reset",
                        },
                    ],
                }
            )

    def test_rejects_bad_transition_targets(self):
        with pytest.raises(ValidationError, match="unknown next node"):
            CallTreeSchema.model_validate(
                {
                    "id": "bad_tree",
                    "brand": "Acme Corp",
                    "root_node_id": "root",
                    "nodes": [
                        {
                            "id": "root",
                            "label": "Root",
                            "prompt": "Press 1.",
                            "input_type": "dtmf",
                            "transitions": [{"input": "1", "next_node_id": "missing"}],
                        }
                    ],
                }
            )

    def test_agent_leaves_use_existing_workflow_intents(self):
        tree = get_call_tree()
        assert tree is not None
        supported_intents = set(list_intents())
        agent_nodes = [node for node in tree.nodes if node.input_type == "speech"]

        assert {node.intent for node in agent_nodes} == supported_intents


class TestIvrBridge:
    """DEV-32 coverage for the ephemeral IVR bridge."""

    def test_start_agent_session_creates_state_and_returns_first_prompt(self, monkeypatch):
        service = make_service(monkeypatch, "password_reset")
        call_sid = "ivr-bridge-1"

        result = start_agent_session(call_sid, "password_reset_agent", service)

        assert result["session_id"] == f"ivr-{call_sid}"
        assert result["resolved"] is False
        assert result["escalated"] is False
        assert "account number" in result["message"].lower()

        call_state = get_call_state(call_sid)
        assert call_state is not None
        assert call_state.agent_session_id == f"ivr-{call_sid}"
        assert call_state.current_node_id == "password_reset_agent"
        assert call_state.intent == "password_reset"

        cleanup_call(call_sid)

    def test_process_agent_turn_reuses_mapped_workflow_session(self, monkeypatch):
        service = make_service(monkeypatch, "password_reset")
        call_sid = "ivr-bridge-2"
        start_agent_session(call_sid, "password_reset_agent", service)

        result = process_agent_turn(call_sid, "12345678", service)

        assert result["session_id"] == f"ivr-{call_sid}"
        assert result["resolved"] is False
        assert "verification code" in result["message"].lower()

        session = service.get_session(f"ivr-{call_sid}")
        assert session.validated_fields["account_id"] == "12345678"

        cleanup_call(call_sid)

    def test_cleanup_removes_call_state(self, monkeypatch):
        service = make_service(monkeypatch, "password_reset")
        call_sid = "ivr-bridge-3"
        start_agent_session(call_sid, "password_reset_agent", service)

        assert get_call_state(call_sid) is not None
        cleanup_call(call_sid)
        assert get_call_state(call_sid) is None


class TestIvrRoutes:
    """DEV-33 coverage for TwiML route behavior."""

    def test_incoming_returns_twiml_with_greeting(self, monkeypatch):
        client = _make_client(monkeypatch)

        response = client.post("/ivr/incoming")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/xml")
        assert "Thank you for calling Acme Corp" in response.text
        assert 'action="/ivr/menu?node_id=root"' in response.text
        assert "<Gather" in response.text

    def test_valid_digit_navigates_to_submenu(self, monkeypatch):
        client = _make_client(monkeypatch)

        response = client.post("/ivr/menu?node_id=root", data={"Digits": "1"})

        assert response.status_code == 200
        assert "billing dispute" in response.text.lower()
        assert 'action="/ivr/menu?node_id=billing_menu"' in response.text

    def test_invalid_digit_repompts_current_menu(self, monkeypatch):
        client = _make_client(monkeypatch)

        response = client.post("/ivr/menu?node_id=root", data={"Digits": "9"})

        assert response.status_code == 200
        assert "not a valid selection" in response.text.lower()
        assert 'action="/ivr/menu?node_id=root"' in response.text

    def test_menu_can_redirect_to_agent_node(self, monkeypatch):
        client = _make_client(monkeypatch)

        response = client.post("/ivr/menu?node_id=account_menu", data={"Digits": "1"})

        assert response.status_code == 200
        assert "<Redirect" in response.text
        assert "/ivr/agent-greeting?node_id=password_reset_agent" in response.text

    def test_agent_turn_processes_speech(self, monkeypatch):
        client = _make_client(monkeypatch)
        call_sid = "ivr-route-1"

        greeting = client.post(
            "/ivr/agent-greeting?node_id=password_reset_agent",
            data={"CallSid": call_sid},
        )
        assert greeting.status_code == 200
        assert "password reset specialist" in greeting.text.lower()
        assert "account number" in greeting.text.lower()
        assert 'action="/ivr/agent-turn?node_id=password_reset_agent"' in greeting.text

        first_turn = client.post(
            "/ivr/agent-turn?node_id=password_reset_agent",
            data={"CallSid": call_sid, "SpeechResult": "12345678"},
        )
        assert first_turn.status_code == 200
        assert "verification code" in first_turn.text.lower()
        assert "<Gather" in first_turn.text

        second_turn = client.post(
            "/ivr/agent-turn?node_id=password_reset_agent",
            data={"CallSid": call_sid, "SpeechResult": "654321"},
        )
        assert second_turn.status_code == 200
        assert "password reset" in second_turn.text.lower()
        assert "<Gather" not in second_turn.text

        cleanup_call(call_sid)

    def test_status_callback_cleans_up_call_state(self, monkeypatch):
        client = _make_client(monkeypatch)
        call_sid = "ivr-route-2"

        client.post("/ivr/agent-greeting?node_id=password_reset_agent", data={"CallSid": call_sid})
        assert get_call_state(call_sid) is not None

        response = client.post(
            "/ivr/status-callback",
            data={"CallSid": call_sid, "CallStatus": "completed"},
        )

        assert response.status_code == 200
        assert response.text.strip() == "<Response />"
        assert get_call_state(call_sid) is None
