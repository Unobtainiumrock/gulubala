"""Pydantic request and response models for the HTTP API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from contracts.models import SessionState


class RouteIntentRequest(BaseModel):
    session_id: str
    utterance: str


class RouteIntentResponse(BaseModel):
    session_id: str
    intent: str
    confidence: float
    needs_disambiguation: bool = False
    escalate: bool = False
    reason: str | None = None


class PlanNextStepRequest(BaseModel):
    session_id: str


class PlanNextStepResponse(BaseModel):
    session_id: str
    next_fields: list[str] = Field(default_factory=list)
    next_questions: list[str] = Field(default_factory=list)
    missing_required_fields: list[str] = Field(default_factory=list)
    escalate: bool = False
    escalation_reason: str | None = None


class SubmitFieldRequest(BaseModel):
    session_id: str
    field_name: str
    value: str
    source: str = "caller"


class SubmitFieldResponse(BaseModel):
    session_id: str
    accepted: bool
    field_name: str
    normalized_value: str | None = None
    retry_count: int = 0
    escalate: bool = False
    escalation_reason: str | None = None
    validation_error: str | None = None


class DispatchActionRequest(BaseModel):
    session_id: str


class DispatchActionResponse(BaseModel):
    session_id: str
    action: str
    status: str
    result: str | None = None
    escalate: bool = False
    escalation_reason: str | None = None


class EscalationSummaryRequest(BaseModel):
    session_id: str


class EscalationSummaryResponse(BaseModel):
    session_id: str
    intent: str | None = None
    escalation_reason: str | None = None
    summary: str
    state: dict[str, Any]


class SessionResponse(BaseModel):
    session: SessionState
