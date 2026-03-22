"""WebSocket dashboard event schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class NodeEnteredEvent(BaseModel):
    """Fired when synchronize_state updates current_fields to a new batch."""

    event_type: Literal["node_entered"] = "node_entered"
    session_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    node_fields: list[str]
    intent: str | None = None
    validated_fields: dict[str, str] = Field(default_factory=dict)
    missing_required_fields: list[str] = Field(default_factory=list)


class TranscriptEvent(BaseModel):
    """Fired when a user or assistant turn is registered."""

    event_type: Literal["transcript"] = "transcript"
    session_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    role: Literal["user", "assistant"]
    content: str
    turn_count: int = 0


class EscalationEvent(BaseModel):
    """Fired when escalation is triggered."""

    event_type: Literal["escalation"] = "escalation"
    session_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reason: str
    intent: str | None = None
    validated_fields: dict[str, str] = Field(default_factory=dict)


class BridgeActiveEvent(BaseModel):
    """Fired when the IVR leg and presenter are joined in a Twilio conference."""

    event_type: Literal["bridge_active"] = "bridge_active"
    session_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    conference_name: str
    presenter_call_sid: str


class CompletedEvent(BaseModel):
    """Fired when a session resolves successfully."""

    event_type: Literal["completed"] = "completed"
    session_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    intent: str | None = None
    action_result: str | None = None
    validated_fields: dict[str, str] = Field(default_factory=dict)
    turn_count: int = 0
    transcript_url: str | None = None


DashboardEvent = (
    NodeEnteredEvent
    | TranscriptEvent
    | EscalationEvent
    | BridgeActiveEvent
    | CompletedEvent
)
