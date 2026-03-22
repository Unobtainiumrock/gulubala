"""FastAPI application exposing the workflow service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

try:
    from fastapi import FastAPI, HTTPException
except ModuleNotFoundError:  # pragma: no cover - exercised when dependency is absent
    FastAPI = None
    HTTPException = RuntimeError


from config.models import SESSION_DB_PATH
from dashboard.ws import get_manager, router as ws_router
from ivr.routes import router as ivr_router
from contracts.api import (
    DemoScenarioResponse,
    DemoStartRequest,
    DemoStartResponse,
    DemoTurnRequest,
    DemoTurnResponse,
    DemoVoiceTurnRequest,
    DispatchActionRequest,
    DispatchActionResponse,
    EscalationSummaryRequest,
    EscalationSummaryResponse,
    HealthResponse,
    PlanNextStepRequest,
    PlanNextStepResponse,
    RouteIntentRequest,
    RouteIntentResponse,
    SubmitDocumentRequest,
    SubmitDocumentResponse,
    SubmitFieldRequest,
    SubmitFieldResponse,
    VoiceEventRequest,
    VoiceEventResponse,
)
from services.orchestrator import CallCenterService
from services.session_store import SQLiteSessionStore

_SERVICE: CallCenterService | None = None


def get_service() -> CallCenterService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = CallCenterService(
            SQLiteSessionStore(SESSION_DB_PATH),
            event_publisher=get_manager().publish_sync,
        )
    return _SERVICE


_logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """On startup: auto-detect ngrok and sync Twilio webhook (best-effort)."""
    try:
        from telephony.ngrok import auto_sync
        result = auto_sync()
        if result:
            _logger.info("Twilio webhook auto-synced: %s", result["voice_url"])
        else:
            _logger.warning("ngrok not detected — start ngrok before uvicorn, or update Twilio manually.")
    except Exception as exc:
        _logger.warning("Twilio webhook sync skipped: %s", exc)
    yield


def create_app():
    if FastAPI is None:
        raise ModuleNotFoundError("FastAPI is not installed. Install requirements to run the HTTP API.")

    app = FastAPI(title="LLM Call Center Agent", version="0.1.0", lifespan=_lifespan)
    app.state.get_service = get_service
    app.include_router(ws_router)
    app.include_router(ivr_router)

    @app.get("/health", response_model=HealthResponse)
    def health():
        return HealthResponse(status="ok")

    @app.get("/demo/scenarios", response_model=list[DemoScenarioResponse])
    def demo_scenarios():
        service = get_service()
        payload = service.list_demo_scenarios()
        return [DemoScenarioResponse.model_validate(item) for item in payload]

    @app.post("/demo/start", response_model=DemoStartResponse)
    def demo_start(request: DemoStartRequest):
        try:
            service = get_service()
            payload = service.start_demo_session(request.scenario_id, channel=request.channel)
            return DemoStartResponse.model_validate(payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/demo/turn", response_model=DemoTurnResponse)
    def demo_turn(request: DemoTurnRequest):
        try:
            service = get_service()
            payload = service.handle_demo_turn(request.session_id, request.utterance)
            return DemoTurnResponse.model_validate(payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/demo/voice-turn", response_model=DemoTurnResponse)
    def demo_voice_turn(request: DemoVoiceTurnRequest):
        try:
            service = get_service()
            payload = service.handle_demo_voice_turn(
                request.session_id,
                request.audio_base64,
                filename=request.filename,
                content_type=request.content_type,
                language=request.language,
            )
            return DemoTurnResponse.model_validate(payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/route-intent", response_model=RouteIntentResponse)
    def route_intent(request: RouteIntentRequest):
        try:
            service = get_service()
            payload = service.route_intent(request.session_id, request.utterance)
            return RouteIntentResponse.model_validate(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/plan-next-step", response_model=PlanNextStepResponse)
    def plan_next_step(request: PlanNextStepRequest):
        try:
            service = get_service()
            payload = service.plan_next_step(request.session_id)
            return PlanNextStepResponse.model_validate(payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/submit-field", response_model=SubmitFieldResponse)
    def submit_field(request: SubmitFieldRequest):
        try:
            service = get_service()
            payload = service.submit_field(
                request.session_id,
                request.field_name,
                request.value,
                source=request.source,
            )
            return SubmitFieldResponse.model_validate(payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/dispatch-action", response_model=DispatchActionResponse)
    def dispatch_action(request: DispatchActionRequest):
        try:
            service = get_service()
            payload = service.dispatch_action(request.session_id)
            return DispatchActionResponse.model_validate(payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/escalation-summary", response_model=EscalationSummaryResponse)
    def escalation_summary(request: EscalationSummaryRequest):
        try:
            service = get_service()
            payload = service.build_escalation_summary(request.session_id)
            return EscalationSummaryResponse.model_validate(payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/voice-event", response_model=VoiceEventResponse)
    def voice_event(request: VoiceEventRequest):
        try:
            service = get_service()
            payload = request.model_dump(exclude_none=True)
            if request.audio_data is not None and request.type in {"transcript", "user_transcript"}:
                from asr.transcribe import transcribe
                chunks = [request.audio_data]
                transcript = transcribe(chunks)
                payload["text"] = transcript
                payload.pop("audio_data", None)
            else:
                payload.pop("audio_data", None)
            result = service.handle_voice_event(payload)
            return VoiceEventResponse.model_validate(result)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/submit-document", response_model=SubmitDocumentResponse)
    def submit_document(request: SubmitDocumentRequest):
        try:
            service = get_service()
            result = service.submit_supporting_document(
                request.session_id, request.document_text,
            )
            return SubmitDocumentResponse(
                session_id=request.session_id, **result,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app


app = create_app() if FastAPI is not None else None
