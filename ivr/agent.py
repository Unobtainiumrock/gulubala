"""Bridge IVR agent nodes into the workflow orchestrator."""

from __future__ import annotations

from typing import Any

from calltree.registry import get_call_tree_node
from ivr.state import IVRCallState, clear_call_state, get_call_state, save_call_state
from services.orchestrator import CallCenterService
from workflows.registry import get_workflow

DEFAULT_TREE_ID = "acme_corp"


def _session_id_for_call(call_sid: str) -> str:
    return f"ivr-{call_sid}"


def start_agent_session(call_sid: str, node_id: str, service: CallCenterService) -> dict[str, Any]:
    """Create or reuse a deterministic workflow session for an IVR call."""
    node = get_call_tree_node(DEFAULT_TREE_ID, node_id)
    if node is None:
        raise KeyError(f"Unknown IVR node '{node_id}'")
    if node.input_type != "speech" or not node.intent:
        raise KeyError(f"IVR node '{node_id}' is not an agent node")

    session_id = _session_id_for_call(call_sid)
    session = service.store.get_session(session_id)
    if session is None:
        session = service.create_session(channel="voice", session_id=session_id)

    workflow = get_workflow(node.intent)
    if workflow is None:
        raise KeyError(f"Missing workflow for intent '{node.intent}'")

    session.channel = "voice"
    session.intent = node.intent
    session.metadata["ivr_call_sid"] = call_sid
    session.metadata["ivr_tree_id"] = DEFAULT_TREE_ID
    session.metadata["ivr_node_id"] = node_id
    service.engine.synchronize_state(session, workflow)

    plan = service.engine.plan_next_step(session, workflow)
    message = " ".join(plan["next_questions"]) if plan["next_questions"] else "Please continue."
    last_turn = session.conversation_history[-1] if session.conversation_history else None
    if last_turn is None or last_turn.role != "assistant" or last_turn.content != message:
        service.engine.register_assistant_turn(session, message)
    service.store.save_session(session)

    save_call_state(
        IVRCallState(
            call_sid=call_sid,
            tree_id=DEFAULT_TREE_ID,
            current_node_id=node_id,
            agent_session_id=session.session_id,
            intent=node.intent,
        )
    )

    return {
        "session_id": session.session_id,
        "message": message,
        "resolved": session.resolved,
        "escalated": session.escalate,
    }


def process_agent_turn(call_sid: str, utterance: str, service: CallCenterService) -> dict[str, Any]:
    """Delegate IVR speech input into the existing workflow conversation engine."""
    call_state = get_call_state(call_sid)
    if call_state is None:
        raise KeyError(f"Unknown IVR call '{call_sid}'")

    result = service.handle_user_turn(call_state.agent_session_id, utterance)
    session = service.get_session(call_state.agent_session_id)
    call_state.current_node_id = session.metadata.get("ivr_node_id", call_state.current_node_id)
    save_call_state(call_state)
    return {
        "session_id": result["session_id"],
        "message": result["message"],
        "resolved": result["resolved"],
        "escalated": result["escalated"],
    }


def cleanup_call(call_sid: str) -> None:
    """Remove transient IVR state after Twilio completes the call."""
    clear_call_state(call_sid)
