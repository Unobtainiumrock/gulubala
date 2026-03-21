from contracts.models import ConversationTurn, SessionState
from contracts.prompts import IntentExtractionResponse, parse_contract
from audio.tts import normalize_tts_text
from validation.validators import (
    get_validator,
    normalize_digit_tokens,
    parse_numeric,
    validate_account_number,
    validate_currency,
    validate_date,
    validate_verification_code,
    validate_zip_code,
)
from workflows.registry import get_workflow, list_intents


def test_workflow_registry_loads_canonical_schema():
    workflow = get_workflow("billing_dispute")

    assert workflow is not None
    assert workflow.field_priority[0] == "account_number"
    assert workflow.get_field("charge_amount").document_extractable is True
    assert any(condition.type == "document_mismatch" for condition in workflow.escalation_conditions)
    assert "cancel_service" in list_intents()


def test_prompt_contract_parsing_round_trip():
    raw = '{"intent":"password_reset","confidence":0.91,"needs_disambiguation":false,"reason":null}'
    parsed = parse_contract(raw, IntentExtractionResponse)

    assert parsed.intent == "password_reset"
    assert parsed.confidence == 0.91


def test_session_state_serialization_round_trip():
    session = SessionState(
        channel="text",
        intent="password_reset",
        validated_fields={"account_id": "12345678"},
        conversation_history=[ConversationTurn(role="user", content="help")],
    )

    restored = SessionState.model_validate_json(session.model_dump_json())

    assert restored.intent == "password_reset"
    assert restored.validated_fields["account_id"] == "12345678"
    assert restored.conversation_history[0].content == "help"


def test_validators_normalize_values():
    assert validate_currency("$49.9") == (True, "$49.90")
    assert validate_date("03/15/2026") == (True, "2026-03-15")
    assert validate_zip_code("94105") == (True, "94105")
    assert parse_numeric("$5,000.55") == 5000.55
    assert get_validator("zip_code")("94105") == (True, "94105")
    assert normalize_digit_tokens("my account ID is 1 2 3 4 5 6 7 8") == "12345678"
    assert validate_account_number("my account ID is one two three four five six seven eight") == (True, "12345678")
    assert validate_verification_code("one two three four five six") == (True, "123456")


def test_tts_text_normalization_rewrites_unfriendly_phrases():
    normalized = normalize_tts_text("Please say your account ID and then enter 123456.")

    assert "account number" in normalized
    assert "1 2 3 4 5 6" in normalized
