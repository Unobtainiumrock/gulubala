"""FastAPI application exposing the workflow service."""

from __future__ import annotations

try:
    from fastapi import FastAPI, HTTPException
except ModuleNotFoundError:  # pragma: no cover - exercised when dependency is absent
    FastAPI = None
    HTTPException = RuntimeError

from config.models import SESSION_DB_PATH
from contracts.api import (
    DispatchActionRequest,
    DispatchActionResponse,
    EscalationSummaryRequest,
    EscalationSummaryResponse,
    PlanNextStepRequest,
    PlanNextStepResponse,
    RouteIntentRequest,
    RouteIntentResponse,
    SubmitFieldRequest,
    SubmitFieldResponse,
)
from services.orchestrator import CallCenterService
from services.session_store import SQLiteSessionStore

_SERVICE: CallCenterService | None = None


def get_service() -> CallCenterService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = CallCenterService(SQLiteSessionStore(SESSION_DB_PATH))
    return _SERVICE


def create_app():
    if FastAPI is None:
        raise ModuleNotFoundError("FastAPI is not installed. Install requirements to run the HTTP API.")

    app = FastAPI(title="LLM Call Center Agent", version="0.1.0")

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

    return app


app = create_app() if FastAPI is not None else None
