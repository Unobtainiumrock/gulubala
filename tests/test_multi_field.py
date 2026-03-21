"""Verification tests for multi-field extraction per turn (V1-V9)."""

import pytest

from contracts.models import SessionState
from contracts.prompts import MultiFieldExtractionResponse, build_multi_field_extraction_prompt
from dialogue.manager import WorkflowEngine
from services.session_store import InMemorySessionStore
from workflows.registry import get_workflow

from tests.conftest import make_service, stub_field_extractor, stub_multi_field_extractor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine(**overrides):
    defaults = dict(
        field_extractor=stub_field_extractor,
        multi_field_extractor=stub_multi_field_extractor,
        summary_builder=lambda payload: "Escalation summary.",
    )
    defaults.update(overrides)
    return WorkflowEngine(**defaults)


def _make_billing_state(engine):
    workflow = get_workflow("billing_dispute")
    session = InMemorySessionStore().create_session(channel="text")
    session.intent = "billing_dispute"
    engine.synchronize_state(session, workflow)
    return session, workflow


# ---------------------------------------------------------------------------
# V1: SessionState model - current_fields / last_questions
# ---------------------------------------------------------------------------

class TestV1SessionStateModel:
    def test_current_fields_is_list(self):
        state = SessionState()
        assert isinstance(state.current_fields, list)
        assert state.current_fields == []

    def test_last_questions_is_list(self):
        state = SessionState()
        assert isinstance(state.last_questions, list)
        assert state.last_questions == []

    def test_old_singular_attributes_absent(self):
        state = SessionState()
        assert not hasattr(state, "current_field")
        assert not hasattr(state, "last_question")


# ---------------------------------------------------------------------------
# V2: Prompt contract - MultiFieldExtractionResponse
# ---------------------------------------------------------------------------

class TestV2PromptContract:
    def test_parse_multi_field_response(self):
        raw = '{"fields": {"account_number": "12345678", "charge_date": null}}'
        parsed = MultiFieldExtractionResponse.model_validate_json(raw)
        assert parsed.fields["account_number"] == "12345678"
        assert parsed.fields["charge_date"] is None

    def test_build_prompt_includes_all_fields(self):
        prompt = build_multi_field_extraction_prompt([
            ("account_number", "string"),
            ("charge_date", "string"),
            ("charge_amount", "string"),
        ])
        assert "account_number" in prompt
        assert "charge_date" in prompt
        assert "charge_amount" in prompt
        assert "multi_field_extraction" in prompt


# ---------------------------------------------------------------------------
# V3: synchronize_state - batch size capping
# ---------------------------------------------------------------------------

class TestV3SynchronizeState:
    def test_four_missing_fields_caps_at_three(self):
        engine = _make_engine()
        session, workflow = _make_billing_state(engine)
        assert len(session.current_fields) == 3
        assert len(session.last_questions) == 3
        assert len(session.missing_required_fields) == 4

    def test_one_missing_field_returns_one(self):
        engine = _make_engine()
        session, workflow = _make_billing_state(engine)
        engine.submit_field(session, workflow, "account_number", "12345678")
        engine.submit_field(session, workflow, "charge_date", "03/10/2026")
        engine.submit_field(session, workflow, "charge_amount", "$49.99")
        assert len(session.current_fields) == 1
        assert session.current_fields[0] == "dispute_reason"

    def test_all_collected_returns_empty(self):
        engine = _make_engine()
        session, workflow = _make_billing_state(engine)
        engine.submit_field(session, workflow, "account_number", "12345678")
        engine.submit_field(session, workflow, "charge_date", "03/10/2026")
        engine.submit_field(session, workflow, "charge_amount", "$49.99")
        engine.submit_field(session, workflow, "dispute_reason", "duplicate charge")
        assert session.current_fields == []
        assert session.last_questions == []


# ---------------------------------------------------------------------------
# V4: _llm_extract_fields - batch extraction method
# ---------------------------------------------------------------------------

class TestV4BatchExtraction:
    def test_stub_extracts_multiple_values(self):
        engine = _make_engine()
        workflow = get_workflow("billing_dispute")
        fields = [workflow.get_field(n) for n in ["account_number", "charge_date", "charge_amount"]]
        result = engine.multi_field_extractor(fields, "12345678 03/10/2026 $49.99")
        assert result["account_number"] == "12345678"
        assert result["charge_date"] == "03/10/2026"
        assert result["charge_amount"] == "$49.99"

    def test_graceful_fallback_on_no_match(self):
        engine = _make_engine()
        workflow = get_workflow("billing_dispute")
        fields = [workflow.get_field("account_number")]
        result = engine.multi_field_extractor(fields, "no digits here")
        assert result == {}

    def test_free_text_uses_remaining_tokens(self):
        engine = _make_engine()
        workflow = get_workflow("billing_dispute")
        fields = [
            workflow.get_field("account_number"),
            workflow.get_field("dispute_reason"),
        ]
        result = engine.multi_field_extractor(fields, "12345678 wrong charge on my bill")
        assert result["account_number"] == "12345678"
        assert "wrong charge" in result["dispute_reason"]


# ---------------------------------------------------------------------------
# V5: attempt_multi_field_capture
# ---------------------------------------------------------------------------

class TestV5MultiFieldCapture:
    def test_three_valid_fields_all_accepted(self):
        engine = _make_engine()
        session, workflow = _make_billing_state(engine)
        results = engine.attempt_multi_field_capture(
            session, workflow, "12345678 03/10/2026 $49.99"
        )
        accepted = [r for r in results if r["accepted"]]
        assert len(accepted) == 3
        assert "account_number" in session.validated_fields
        assert "charge_date" in session.validated_fields
        assert "charge_amount" in session.validated_fields

    def test_partial_extraction_keeps_valid(self):
        engine = _make_engine()
        session, workflow = _make_billing_state(engine)
        # Pre-fill account_number so it's not in missing_fields
        engine.submit_field(session, workflow, "account_number", "12345678")
        # Now "03/10/2026" only matches charge_date
        results = engine.attempt_multi_field_capture(
            session, workflow, "03/10/2026"
        )
        assert "charge_date" in session.validated_fields
        assert "charge_amount" not in session.validated_fields

    def test_escalation_on_max_retries(self):
        """Use password_reset which has a retry_limit escalation condition."""
        engine = _make_engine()
        workflow = get_workflow("password_reset")
        session = InMemorySessionStore().create_session(channel="text")
        session.intent = "password_reset"
        engine.synchronize_state(session, workflow)
        # Pre-fill account_id so only verification_code remains
        engine.submit_field(session, workflow, "account_id", "12345678")
        session.retry_counts["verification_code"] = 2
        # "12" is 2 digits - too short for verification_code validator (4-8 digits)
        results = engine.attempt_multi_field_capture(
            session, workflow, "12"
        )
        assert session.escalate is True
        assert session.escalation_reason == "validation_retry_limit"

    def test_no_fields_extracted_returns_empty(self):
        """With only structured fields missing, pure text yields no matches."""
        engine = _make_engine()
        session, workflow = _make_billing_state(engine)
        # Pre-fill dispute_reason so only structured fields remain
        engine.submit_field(session, workflow, "dispute_reason", "test reason")
        results = engine.attempt_multi_field_capture(
            session, workflow, "hello there"
        )
        assert results == []


# ---------------------------------------------------------------------------
# V6: plan_next_step - returns lists
# ---------------------------------------------------------------------------

class TestV6PlanNextStep:
    def test_returns_next_fields_list(self):
        engine = _make_engine()
        session, workflow = _make_billing_state(engine)
        plan = engine.plan_next_step(session, workflow)
        assert "next_fields" in plan
        assert "next_questions" in plan
        assert isinstance(plan["next_fields"], list)
        assert isinstance(plan["next_questions"], list)
        assert len(plan["next_fields"]) == 3

    def test_no_singular_keys(self):
        engine = _make_engine()
        session, workflow = _make_billing_state(engine)
        plan = engine.plan_next_step(session, workflow)
        assert "next_field" not in plan
        assert "next_question" not in plan


# ---------------------------------------------------------------------------
# V7: handle_user_turn integration
# ---------------------------------------------------------------------------

class TestV7Integration:
    def test_billing_dispute_multi_field_single_turn(self, monkeypatch):
        service = make_service(monkeypatch, "billing_dispute")
        session = service.create_session(channel="text")

        # Turn 1: classify intent; stub also extracts dispute_reason from free text
        service.handle_user_turn(session.session_id, "I need to dispute a charge on my bill.")
        state = service.get_session(session.session_id)
        assert "dispute_reason" in state.validated_fields

        # Turn 2: provide remaining 3 structured fields at once
        response = service.handle_user_turn(
            session.session_id, "12345678 03/01/2026 $95.00"
        )
        state = service.get_session(session.session_id)
        assert "account_number" in state.validated_fields
        assert "charge_date" in state.validated_fields
        assert "charge_amount" in state.validated_fields
        assert response["resolved"] is True
        assert "Dispute case opened" in response["message"]

    def test_billing_dispute_fewer_turns_than_before(self, monkeypatch):
        """Old flow: 5 turns. New flow: 2 turns (intent+reason, then 3 fields)."""
        service = make_service(monkeypatch, "billing_dispute")
        session = service.create_session(channel="text")

        service.handle_user_turn(session.session_id, "I need to dispute a charge.")
        response = service.handle_user_turn(session.session_id, "12345678 03/01/2026 $95.00")

        assert response["resolved"] is True
        state = service.get_session(session.session_id)
        assert state.turn_count == 2


# ---------------------------------------------------------------------------
# V8: Existing tests still pass - covered by test_engine_and_service.py
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# V9: DTMF voice path
# ---------------------------------------------------------------------------

class TestV9DTMFPath:
    def test_dtmf_uses_first_current_field(self, monkeypatch):
        service = make_service(monkeypatch, "password_reset")
        session = service.create_session(channel="voice")

        # Route intent first
        service.route_intent(session.session_id, "I need to reset my password.")
        state = service.get_session(session.session_id)
        assert "account_id" in state.current_fields

        # DTMF event should target account_id (first current field)
        result = service.handle_voice_event({
            "type": "dtmf",
            "session_id": session.session_id,
            "digits": "12345678",
        })
        state = service.get_session(session.session_id)
        assert state.validated_fields.get("account_id") == "12345678"
