"""Ephemeral IVR call state."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass
class IVRCallState:
    """Transient IVR routing state keyed by Twilio CallSid."""

    call_sid: str
    tree_id: str
    current_node_id: str
    agent_session_id: str
    intent: str


_CALL_STATES: dict[str, IVRCallState] = {}
_LOCK = Lock()


def get_call_state(call_sid: str) -> IVRCallState | None:
    with _LOCK:
        return _CALL_STATES.get(call_sid)


def save_call_state(state: IVRCallState) -> IVRCallState:
    with _LOCK:
        _CALL_STATES[state.call_sid] = state
    return state


def clear_call_state(call_sid: str) -> None:
    with _LOCK:
        _CALL_STATES.pop(call_sid, None)
