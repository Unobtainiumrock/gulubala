"""Pydantic request and response models for the HTTP API."""

from __future__ import annotations

from typing import Any, Literal

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


class VoiceAssistantOutput(BaseModel):
    type: Literal["assistant_output"] = "assistant_output"
    session_id: str
    text: str
    ssml: str | None = None
    voice: str | None = None
    barge_in: bool = True


class VoiceResponseEnvelope(BaseModel):
    text: str
    spoken_text: str
    ssml: str | None = None
    voice_provider: VoiceAssistantOutput | None = None


class SubmitDocumentRequest(BaseModel):
    session_id: str
    document_text: str


class SubmitDocumentResponse(BaseModel):
    session_id: str
    job_id: str
    status: str
    fields: dict[str, str] = Field(default_factory=dict)
    confidence: dict[str, float] = Field(default_factory=dict)
    mismatches: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str


class SessionResponse(BaseModel):
    session: SessionState


class DemoScenarioResponse(BaseModel):
    id: str
    title: str
    intent: str
    tagline: str
    summary: str
    opening_message: str
    seed_script: list[dict[str, str]] = Field(default_factory=list)
    demo_goal: str


class DemoStartRequest(BaseModel):
    scenario_id: str
    channel: str = "voice"


class DemoStartResponse(BaseModel):
    session_id: str
    scenario: DemoScenarioResponse
    message: str
    docs_url: str = "/docs"
    voice_response: VoiceResponseEnvelope | None = None


class DemoTurnRequest(BaseModel):
    session_id: str
    utterance: str


class DemoVoiceTurnRequest(BaseModel):
    session_id: str
    audio_base64: str
    filename: str = "recording.webm"
    content_type: str = "audio/webm"
    language: str = "English"


class DemoTurnResponse(BaseModel):
    session_id: str
    transcript: str | None = None
    message: str
    resolved: bool
    escalated: bool
    scenario_id: str | None = None
    action_result: str | None = None
    voice_response: VoiceResponseEnvelope | None = None


class BlandToolRequest(BaseModel):
    call_id: str
    utterance: str | None = None


class BlandToolResponse(BaseModel):
    message: str
    resolved: bool = False
    escalated: bool = False
    session_id: str | None = None
