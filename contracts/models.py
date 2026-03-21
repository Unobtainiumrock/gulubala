"""Typed models for workflow schemas and serialized session state."""

from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


ComparisonOperator = Literal["==", "!=", ">", ">=", "<", "<="]
EscalationType = Literal[
    "user_request_human",
    "retry_limit",
    "numeric_threshold",
    "flag_equals",
    "backend_failure",
    "loop_stall",
    "document_mismatch",
    "low_intent_confidence",
]


class ValidatorSpec(BaseModel):
    """Schema-level validator metadata."""

    type: str
    name: str | None = None
    pattern: str | None = None
    values: list[str] = Field(default_factory=list)


class FieldDefinition(BaseModel):
    """Field metadata used by the workflow engine."""

    name: str
    type: str = "string"
    prompt: str
    validator: str = "non_empty"
    dtmf_allowed: bool = False
    document_extractable: bool = False


class ConditionalRequirement(BaseModel):
    """A field that becomes required only when another value matches."""

    field: str
    depends_on: str
    operator: ComparisonOperator = "=="
    value: Any


class EscalationCondition(BaseModel):
    """Machine-evaluable escalation rule."""

    type: EscalationType
    reason: str
    field: str | None = None
    operator: ComparisonOperator | None = None
    value: Any = None


class WorkflowSchema(BaseModel):
    """Canonical workflow schema loaded from JSON."""

    intent: str
    required_fields: list[FieldDefinition]
    optional_fields: list[FieldDefinition] = Field(default_factory=list)
    field_priority: list[str] = Field(default_factory=list)
    validators: dict[str, ValidatorSpec] = Field(default_factory=dict)
    conditional_requirements: list[ConditionalRequirement] = Field(default_factory=list)
    action: str
    escalation_conditions: list[EscalationCondition] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        optional_fields = data.get("optional_fields", [])
        if optional_fields and isinstance(optional_fields[0], str):
            data["optional_fields"] = [
                {
                    "name": field_name,
                    "type": "string",
                    "prompt": f"Please provide your {field_name.replace('_', ' ')}.",
                    "validator": "non_empty",
                    "dtmf_allowed": False,
                    "document_extractable": False,
                }
                for field_name in optional_fields
            ]
        return data

    @model_validator(mode="after")
    def _validate_references(self) -> "WorkflowSchema":
        field_names = {field.name for field in self.required_fields + self.optional_fields}

        if not self.field_priority:
            self.field_priority = [field.name for field in self.required_fields + self.optional_fields]

        missing_from_priority = field_names.difference(self.field_priority)
        if missing_from_priority:
            self.field_priority.extend(sorted(missing_from_priority))

        unknown_priority_fields = [name for name in self.field_priority if name not in field_names]
        if unknown_priority_fields:
            raise ValueError(f"Unknown field(s) in field_priority: {unknown_priority_fields}")

        for requirement in self.conditional_requirements:
            if requirement.field not in field_names:
                raise ValueError(f"Conditional field '{requirement.field}' is not defined")
            if requirement.depends_on not in field_names:
                raise ValueError(f"Conditional dependency '{requirement.depends_on}' is not defined")

        for field_name in self.validators:
            if field_name not in field_names:
                raise ValueError(f"Validator references unknown field '{field_name}'")

        return self

    def get_field(self, name: str) -> FieldDefinition | None:
        for field in self.required_fields + self.optional_fields:
            if field.name == name:
                return field
        return None

    def iter_required_field_names(self) -> list[str]:
        return [field.name for field in self.required_fields]


class ConversationTurn(BaseModel):
    """Conversation transcript item stored in state."""

    role: Literal["user", "assistant", "system"]
    content: str


class DocumentExtractionResult(BaseModel):
    """Normalized document extraction output for Eigen integration."""

    job_id: str
    status: Literal["completed", "needs_review", "failed"]
    fields: dict[str, str] = Field(default_factory=dict)
    confidence: dict[str, float] = Field(default_factory=dict)
    source: str = "heuristic"


class SessionState(BaseModel):
    """Serializable workflow state for a single caller session."""

    session_id: str = Field(default_factory=lambda: uuid4().hex)
    channel: str = "text"
    intent: str | None = None
    confidence: float = 0.0
    collected_fields: dict[str, str] = Field(default_factory=dict)
    validated_fields: dict[str, str] = Field(default_factory=dict)
    missing_required_fields: list[str] = Field(default_factory=list)
    current_field: str | None = None
    last_question: str | None = None
    retry_counts: dict[str, int] = Field(default_factory=dict)
    escalate: bool = False
    escalation_reason: str | None = None
    action_status: str | None = None
    action_result: str | None = None
    resolved: bool = False
    turn_count: int = 0
    conversation_history: list[ConversationTurn] = Field(default_factory=list)
    document_results: dict[str, DocumentExtractionResult] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

