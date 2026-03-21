"""Shared application service for CLI, API, Boson, and document flows."""

from __future__ import annotations

from typing import Any

from actions.backend import execute_action
from boson.adapter import BosonAdapter
from dialogue.manager import WorkflowEngine
from documents.eigen_adapter import EigenDocumentAdapter
from intents.router import classify_intent
from services.logging import log_event
from services.session_store import SessionStore
from workflows.registry import get_workflow


class CallCenterService:
    """Coordinate sessions, workflow planning, action dispatch, and integrations."""

    def __init__(
        self,
        store: SessionStore,
        engine: WorkflowEngine | None = None,
        document_adapter: EigenDocumentAdapter | None = None,
        boson_adapter: BosonAdapter | None = None,
    ):
        self.store = store
        self.engine = engine or WorkflowEngine()
        self.document_adapter = document_adapter or EigenDocumentAdapter()
        self.boson_adapter = boson_adapter or BosonAdapter()

    def create_session(self, channel: str = "text", session_id: str | None = None):
        session = self.store.create_session(channel=channel, session_id=session_id)
        log_event("session_created", session, channel=channel)
        return session

    def get_session(self, session_id: str):
        session = self.store.get_session(session_id)
        if session is None:
            raise KeyError(f"Unknown session_id '{session_id}'")
        return session

    def route_intent(self, session_id: str, utterance: str) -> dict[str, Any]:
        session = self._get_or_create_session(session_id, channel="api")
        result = classify_intent(utterance)
        session.confidence = result.get("confidence", 0.0)
        session.metadata["needs_disambiguation"] = result.get("needs_disambiguation", False)
        session.metadata["intent_reason"] = result.get("reason")
        if result.get("intent") != "unsupported":
            session.intent = result.get("intent")
        if result.get("escalate"):
            session.escalate = True
            session.escalation_reason = result.get("reason") or "low_intent_confidence"

        if session.intent and not session.escalate:
            workflow = get_workflow(session.intent)
            if workflow is not None:
                self.engine.synchronize_state(session, workflow)

        self.store.save_session(session)
        log_event("intent_routed", session, route=result)
        return {
            "session_id": session.session_id,
            **result,
        }

    def plan_next_step(self, session_id: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        if not session.intent:
            result = {
                "session_id": session.session_id,
                "next_field": None,
                "next_question": None,
                "missing_required_fields": [],
                "escalate": session.escalate,
                "escalation_reason": session.escalation_reason,
            }
            log_event("next_step_planned", session, plan=result)
            return result

        workflow = get_workflow(session.intent)
        if workflow is None:
            session.escalate = True
            session.escalation_reason = "missing_workflow"
            self.store.save_session(session)
            raise KeyError(f"Missing workflow for intent '{session.intent}'")

        plan = self.engine.plan_next_step(session, workflow)
        self.store.save_session(session)
        log_event("next_step_planned", session, plan=plan)
        return {
            "session_id": session.session_id,
            **plan,
        }

    def submit_field(self, session_id: str, field_name: str, value: str, source: str = "caller") -> dict[str, Any]:
        session = self.get_session(session_id)
        workflow = self._require_workflow(session)
        result = self.engine.submit_field(session, workflow, field_name, value, source=source)
        self.store.save_session(session)
        log_event("field_submitted", session, submission=result)
        return {
            "session_id": session.session_id,
            **result,
        }

    def dispatch_action(self, session_id: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        workflow = self._require_workflow(session)
        self.engine.synchronize_state(session, workflow)
        if session.missing_required_fields:
            result = {
                "session_id": session.session_id,
                "action": workflow.action,
                "status": "blocked",
                "result": None,
                "escalate": session.escalate,
                "escalation_reason": session.escalation_reason,
            }
            log_event("action_blocked", session, result=result)
            return result

        try:
            action_result = execute_action(workflow.action, session.validated_fields)
            if isinstance(action_result, str) and action_result.startswith("Error:"):
                raise RuntimeError(action_result)
            session.action_status = "completed"
            session.action_result = action_result
            session.resolved = True
            result = {
                "session_id": session.session_id,
                "action": workflow.action,
                "status": "completed",
                "result": action_result,
                "escalate": False,
                "escalation_reason": None,
            }
        except Exception as exc:
            session.action_status = "failed"
            self.engine.evaluate_escalation(session, workflow)
            if not session.escalation_reason:
                session.escalate = True
                session.escalation_reason = "backend_failure"
            result = {
                "session_id": session.session_id,
                "action": workflow.action,
                "status": "failed",
                "result": str(exc),
                "escalate": True,
                "escalation_reason": session.escalation_reason,
            }
        self.store.save_session(session)
        log_event("action_dispatched", session, result=result)
        return result

    def build_escalation_summary(self, session_id: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        workflow = get_workflow(session.intent) if session.intent else None
        summary = self.engine.build_escalation_summary(session, workflow)
        state = {
            "validated_fields": dict(session.validated_fields),
            "missing_required_fields": list(session.missing_required_fields),
            "retry_counts": dict(session.retry_counts),
            "action_status": session.action_status,
        }
        result = {
            "session_id": session.session_id,
            "intent": session.intent,
            "escalation_reason": session.escalation_reason,
            "summary": summary,
            "state": state,
        }
        log_event("escalation_summary_built", session, summary=result)
        return result

    def submit_supporting_document(self, session_id: str, document_text: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        workflow = self._require_workflow(session)
        extraction = self.document_adapter.extract_fields(workflow, document_text)
        session.document_results["supporting_document"] = extraction
        mismatches = self._compare_document_against_state(session, extraction.fields)
        if mismatches:
            session.metadata["document_mismatch"] = True
            session.metadata["document_mismatch_fields"] = mismatches
            self.engine.evaluate_escalation(session, workflow)
        self.store.save_session(session)
        result = extraction.model_dump()
        result["mismatches"] = mismatches
        log_event("document_processed", session, result=result)
        return result

    def handle_user_turn(self, session_id: str, utterance: str) -> dict[str, Any]:
        session = self.get_session(session_id)
        self.engine.register_user_turn(session, utterance)
        self.store.save_session(session)

        if self.engine.detect_human_request(utterance):
            session.metadata["user_requested_human"] = True
            workflow = get_workflow(session.intent) if session.intent else None
            if workflow is not None:
                self.engine.evaluate_escalation(session, workflow)
            else:
                session.escalate = True
                session.escalation_reason = "user_request_human"
            self.store.save_session(session)
            summary = self.build_escalation_summary(session.session_id)
            session = self.get_session(session.session_id)
            message = f"I understand. Let me connect you with a human agent. {summary['summary']}"
            self.engine.register_assistant_turn(session, message)
            self.store.save_session(session)
            log_event("conversation_turn", session, message=message)
            return {
                "session_id": session.session_id,
                "message": message,
                "resolved": session.resolved,
                "escalated": session.escalate,
            }

        if not session.intent:
            route = self.route_intent(session.session_id, utterance)
            session = self.get_session(session.session_id)
            if route.get("escalate"):
                summary = self.build_escalation_summary(session.session_id)
                message = (
                    "I need to connect you with a human agent so we can handle this correctly. "
                    f"{summary['summary']}"
                )
                self.engine.register_assistant_turn(session, message)
                self.store.save_session(session)
                log_event("conversation_turn", session, message=message)
                return {
                    "session_id": session.session_id,
                    "message": message,
                    "resolved": session.resolved,
                    "escalated": session.escalate,
                }

        workflow = self._require_workflow(session)
        submission = self.engine.attempt_field_capture(session, workflow, utterance)
        self.store.save_session(session)

        if session.escalate:
            summary = self.build_escalation_summary(session.session_id)
            session = self.get_session(session.session_id)
            message = f"I’m handing this to a human agent. {summary['summary']}"
        elif submission and not submission["accepted"]:
            message = self.engine.build_retry_question(
                workflow,
                submission["field_name"],
                submission["validation_error"] or "That information did not validate.",
            )
        else:
            plan = self.engine.plan_next_step(session, workflow)
            self.store.save_session(session)
            if not plan["missing_required_fields"]:
                dispatch = self.dispatch_action(session.session_id)
                session = self.get_session(session.session_id)
                if dispatch["status"] == "completed":
                    message = session.action_result or "Your request is complete."
                else:
                    summary = self.build_escalation_summary(session.session_id)
                    message = f"I need to connect you with a human agent. {summary['summary']}"
            else:
                message = plan["next_question"] or "Please continue."

        self.engine.register_assistant_turn(session, message)
        self.store.save_session(session)
        log_event("conversation_turn", session, message=message)
        return {
            "session_id": session.session_id,
            "message": message,
            "resolved": session.resolved,
            "escalated": session.escalate,
        }

    def handle_voice_event(self, event: dict[str, Any]) -> dict[str, Any]:
        normalized = self.boson_adapter.normalize_event(event)
        session = self._get_or_create_session(normalized.session_id, channel="voice")

        if normalized.event_type == "transcript":
            return self.handle_user_turn(session.session_id, normalized.utterance or "")

        if normalized.event_type == "dtmf":
            workflow = self._require_workflow(session)
            self.engine.synchronize_state(session, workflow)
            current_field = workflow.get_field(session.current_field or "")
            if current_field is None or not current_field.dtmf_allowed:
                return {
                    "session_id": session.session_id,
                    "message": "DTMF input is not available for the current field.",
                    "resolved": session.resolved,
                    "escalated": session.escalate,
                }
            result = self.submit_field(session.session_id, current_field.name, normalized.digits or "", source="dtmf")
            session = self.get_session(session.session_id)
            if result["accepted"]:
                plan = self.plan_next_step(session.session_id)
                message = plan["next_question"] or "Thanks. I have that information."
            else:
                message = self.engine.build_retry_question(
                    workflow,
                    current_field.name,
                    result["validation_error"] or "That input did not validate.",
                )
            self.engine.register_assistant_turn(session, message)
            self.store.save_session(session)
            return {
                "session_id": session.session_id,
                "message": message,
                "resolved": session.resolved,
                "escalated": session.escalate,
            }

        if normalized.event_type == "interrupt":
            session.metadata["boson_interrupted"] = True
            self.store.save_session(session)
            log_event("voice_interrupt", session, metadata=normalized.metadata)
            return {
                "session_id": session.session_id,
                "message": "Interruption registered.",
                "resolved": session.resolved,
                "escalated": session.escalate,
            }

        session.metadata["last_assistant_output"] = normalized.utterance
        self.store.save_session(session)
        log_event("voice_assistant_output", session, metadata=normalized.metadata)
        return {
            "session_id": session.session_id,
            "message": normalized.utterance or "",
            "resolved": session.resolved,
            "escalated": session.escalate,
        }

    def _compare_document_against_state(self, session, extracted_fields: dict[str, str]) -> list[str]:
        mismatches = []
        for field_name, extracted_value in extracted_fields.items():
            current_value = session.validated_fields.get(field_name)
            if current_value and current_value != extracted_value:
                mismatches.append(field_name)
        return mismatches

    def _get_or_create_session(self, session_id: str, channel: str):
        session = self.store.get_session(session_id)
        if session is not None:
            return session
        return self.store.create_session(channel=channel, session_id=session_id)

    def _require_workflow(self, session):
        if not session.intent:
            raise KeyError("Session has no active intent")
        workflow = get_workflow(session.intent)
        if workflow is None:
            raise KeyError(f"Missing workflow for intent '{session.intent}'")
        return workflow
