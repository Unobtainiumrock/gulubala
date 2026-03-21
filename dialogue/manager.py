"""Deterministic workflow engine and escalation handling."""

from __future__ import annotations

from typing import Any, Callable

from client.eigen import chat_completion
from config.models import GPT_OSS_MODEL, HIGGS_CHAT_MODEL, MAX_VALIDATION_RETRIES, MULTI_FIELD_BATCH_SIZE
from contracts.models import ConversationTurn, EscalationCondition, FieldDefinition, SessionState, WorkflowSchema
from contracts.prompts import (
    EscalationSummaryResponse,
    FieldExtractionResponse,
    MultiFieldExtractionResponse,
    build_escalation_summary_prompt,
    build_field_extraction_prompt,
    build_multi_field_extraction_prompt,
    parse_contract,
)
from validation.validators import get_validator, parse_numeric

FieldExtractor = Callable[[FieldDefinition, str], str | None]
MultiFieldExtractor = Callable[[list[FieldDefinition], str], dict[str, str]]
SummaryBuilder = Callable[[dict[str, Any]], str]

_HUMAN_REQUEST_PHRASES = (
    "speak to a human",
    "talk to a person",
    "real person",
    "agent please",
    "supervisor",
    "representative",
)


def _compare_values(left: Any, operator: str, right: Any) -> bool:
    if operator == "==":
        return left == right
    if operator == "!=":
        return left != right

    left_numeric = parse_numeric(left)
    right_numeric = parse_numeric(right)
    if left_numeric is None or right_numeric is None:
        return False
    if operator == ">":
        return left_numeric > right_numeric
    if operator == ">=":
        return left_numeric >= right_numeric
    if operator == "<":
        return left_numeric < right_numeric
    if operator == "<=":
        return left_numeric <= right_numeric
    return False


class WorkflowEngine:
    """Pure orchestration logic for schema-driven call handling."""

    def __init__(
        self,
        field_extractor: FieldExtractor | None = None,
        multi_field_extractor: MultiFieldExtractor | None = None,
        summary_builder: SummaryBuilder | None = None,
    ):
        self.field_extractor = field_extractor or self._llm_extract_field
        self.multi_field_extractor = multi_field_extractor or self._llm_extract_fields
        self.summary_builder = summary_builder or self._llm_build_summary

    def register_user_turn(self, state: SessionState, utterance: str) -> None:
        state.turn_count += 1
        state.conversation_history.append(ConversationTurn(role="user", content=utterance))

    def register_assistant_turn(self, state: SessionState, message: str) -> None:
        state.conversation_history.append(ConversationTurn(role="assistant", content=message))

    def detect_human_request(self, utterance: str) -> bool:
        lowered = utterance.lower()
        return any(phrase in lowered for phrase in _HUMAN_REQUEST_PHRASES)

    def synchronize_state(self, state: SessionState, workflow: WorkflowSchema) -> None:
        active_required = self._active_required_field_names(state, workflow)
        state.missing_required_fields = [
            field_name
            for field_name in workflow.field_priority
            if field_name in active_required and field_name not in state.validated_fields
        ]
        batch = state.missing_required_fields[:MULTI_FIELD_BATCH_SIZE]
        state.current_fields = batch
        state.last_questions = [
            field.prompt
            for name in batch
            if (field := workflow.get_field(name)) is not None
        ]

    def plan_next_step(self, state: SessionState, workflow: WorkflowSchema) -> dict[str, Any]:
        self.synchronize_state(state, workflow)
        escalation_reason = self.evaluate_escalation(state, workflow)
        if escalation_reason:
            next_fields: list[str] = []
            next_questions: list[str] = []
        else:
            next_fields = list(state.current_fields)
            next_questions = list(state.last_questions)
        return {
            "intent": workflow.intent,
            "missing_required_fields": list(state.missing_required_fields),
            "next_fields": next_fields,
            "next_questions": next_questions,
            "escalate": state.escalate,
            "escalation_reason": state.escalation_reason,
        }

    def attempt_multi_field_capture(
        self,
        state: SessionState,
        workflow: WorkflowSchema,
        utterance: str,
    ) -> list[dict[str, Any]]:
        self.synchronize_state(state, workflow)
        if not state.missing_required_fields:
            return []

        # Resolve all missing fields to FieldDefinition objects
        missing_fields = [
            field
            for name in state.missing_required_fields
            if (field := workflow.get_field(name)) is not None
        ]
        if not missing_fields:
            return []

        extracted = self.multi_field_extractor(missing_fields, utterance)
        if not extracted:
            return []

        results = []
        for field in missing_fields:
            value = extracted.get(field.name)
            if value is None:
                continue
            result = self.submit_field(state, workflow, field.name, value, source="utterance")
            results.append(result)
            if state.escalate:
                return results

        return results

    def submit_field(
        self,
        state: SessionState,
        workflow: WorkflowSchema,
        field_name: str,
        value: str,
        source: str = "caller",
    ) -> dict[str, Any]:
        field = workflow.get_field(field_name)
        if field is None:
            return {
                "accepted": False,
                "field_name": field_name,
                "normalized_value": None,
                "retry_count": 0,
                "escalate": state.escalate,
                "escalation_reason": state.escalation_reason,
                "validation_error": "Unknown field.",
            }

        validator = get_validator(field.validator, workflow.validators.get(field_name))
        valid, result = validator(value)

        if valid:
            state.collected_fields[field_name] = result
            state.validated_fields[field_name] = result
            state.retry_counts.pop(field_name, None)
            state.metadata["last_input_source"] = source
            if field is not None and field.document_extractable:
                state.metadata["document_mismatch"] = False
                state.metadata.pop("document_mismatch_fields", None)
            self.synchronize_state(state, workflow)
            self.evaluate_escalation(state, workflow)
            return {
                "accepted": True,
                "field_name": field_name,
                "normalized_value": result,
                "retry_count": 0,
                "escalate": state.escalate,
                "escalation_reason": state.escalation_reason,
                "validation_error": None,
            }

        retry_count = state.retry_counts.get(field_name, 0) + 1
        state.retry_counts[field_name] = retry_count
        self.synchronize_state(state, workflow)
        self.evaluate_escalation(state, workflow)
        return {
            "accepted": False,
            "field_name": field_name,
            "normalized_value": None,
            "retry_count": retry_count,
            "escalate": state.escalate,
            "escalation_reason": state.escalation_reason,
            "validation_error": result,
        }

    def build_retry_question(self, workflow: WorkflowSchema, field_name: str, validation_error: str) -> str:
        field = workflow.get_field(field_name)
        if field is None:
            return validation_error
        return f"{validation_error} {field.prompt}"

    def evaluate_escalation(self, state: SessionState, workflow: WorkflowSchema) -> str | None:
        if state.escalate and state.escalation_reason:
            return state.escalation_reason

        for condition in workflow.escalation_conditions:
            if self._condition_matches(condition, state):
                state.escalate = True
                state.escalation_reason = condition.reason
                return condition.reason
        return None

    def build_escalation_summary(self, state: SessionState, workflow: WorkflowSchema | None) -> str:
        summary_payload = {
            "session_id": state.session_id,
            "intent": state.intent,
            "validated_fields": state.validated_fields,
            "missing_required_fields": state.missing_required_fields,
            "retry_counts": state.retry_counts,
            "escalation_reason": state.escalation_reason,
            "last_questions": state.last_questions,
            "action_status": state.action_status,
            "history": [turn.model_dump() for turn in state.conversation_history[-6:]],
            "workflow": workflow.intent if workflow else None,
        }
        try:
            return self.summary_builder(summary_payload)
        except Exception:
            blocked_field = ", ".join(state.current_fields) or "none"
            return (
                f"Issue: {state.intent or 'unclassified'}. "
                f"Validated fields: {state.validated_fields}. "
                f"Blocked on: {blocked_field}. "
                f"Escalation reason: {state.escalation_reason or 'unspecified'}."
            )

    def _active_required_field_names(self, state: SessionState, workflow: WorkflowSchema) -> list[str]:
        required = set(workflow.iter_required_field_names())
        for conditional in workflow.conditional_requirements:
            dependency_value = (
                state.validated_fields.get(conditional.depends_on)
                or state.metadata.get(conditional.depends_on)
            )
            if _compare_values(dependency_value, conditional.operator, conditional.value):
                required.add(conditional.field)
        return [field_name for field_name in workflow.field_priority if field_name in required]

    def _condition_matches(self, condition: EscalationCondition, state: SessionState) -> bool:
        if condition.type == "user_request_human":
            return bool(state.metadata.get("user_requested_human"))
        if condition.type == "retry_limit":
            retries = state.retry_counts.get(condition.field or "", 0)
            target = condition.value if condition.value is not None else MAX_VALIDATION_RETRIES
            return _compare_values(retries, condition.operator or ">=", target)
        if condition.type == "numeric_threshold":
            current_value = state.validated_fields.get(condition.field or "")
            return _compare_values(current_value, condition.operator or ">", condition.value)
        if condition.type == "flag_equals":
            current_value = state.metadata.get(condition.field or "")
            return _compare_values(current_value, condition.operator or "==", condition.value)
        if condition.type == "backend_failure":
            return state.action_status == "failed"
        if condition.type == "loop_stall":
            current_value = state.turn_count if condition.field == "turn_count" else state.metadata.get(condition.field or "")
            return _compare_values(current_value, condition.operator or ">=", condition.value)
        if condition.type == "document_mismatch":
            return bool(state.metadata.get("document_mismatch"))
        if condition.type == "low_intent_confidence":
            return _compare_values(state.confidence, condition.operator or "<", condition.value)
        return False

    def _llm_extract_field(self, field: FieldDefinition, utterance: str) -> str | None:
        prompt = build_field_extraction_prompt(field.name, field.type)
        raw = chat_completion(
            model=HIGGS_CHAT_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": utterance},
            ],
            temperature=0.1,
            max_tokens=128,
        )
        try:
            parsed = parse_contract(raw, FieldExtractionResponse)
            return parsed.value if parsed.found else None
        except Exception:
            value = raw.strip()
            return None if value in {"", "NOT_FOUND"} else value

    def _llm_extract_fields(self, fields: list[FieldDefinition], utterance: str) -> dict[str, str]:
        """Extract multiple field values from the utterance in a single LLM call."""
        prompt = build_multi_field_extraction_prompt(
            [(f.name, f.type) for f in fields]
        )
        raw = chat_completion(
            model=HIGGS_CHAT_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": utterance},
            ],
            temperature=0.1,
            max_tokens=256,
        )
        try:
            parsed = parse_contract(raw, MultiFieldExtractionResponse)
            return {k: v for k, v in parsed.fields.items() if v is not None}
        except Exception:
            return {}

    def _llm_build_summary(self, summary_payload: dict[str, Any]) -> str:
        prompt = build_escalation_summary_prompt(summary_payload)
        raw = chat_completion(
            model=GPT_OSS_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Build the escalation summary."},
            ],
            temperature=0.2,
            max_tokens=256,
        )
        parsed = parse_contract(raw, EscalationSummaryResponse)
        return parsed.summary
