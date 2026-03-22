import audio.tts as tts_mod
import pytest

from contracts.models import ConversationTurn, SessionState
from contracts.prompts import (
    IntentExtractionResponse,
    IvrClassificationResponse,
    parse_contract,
)
from audio.tts import build_ssml, build_voice_response, normalize_tts_text, realize_spoken_text
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


def test_ivr_classification_accepts_trailing_comma_before_closing_brace():
    raw = """{
  "category": "menu",
  "confidence": 0.99,
  "options": {"1": "Billing", "2": "Account services", "3": "Order support"},
  "requested_info": null,
  "transcript_snippet": "Press 1 for billing",
}"""
    parsed = parse_contract(raw, IvrClassificationResponse)
    assert parsed.category == "menu"
    assert parsed.options is not None
    assert parsed.options.get("1") == "Billing"


def test_ivr_classification_parses_json_after_preamble():
    raw = """Here is the analysis:
{"category": "menu", "confidence": 1.0, "options": {"1": "X"}, "requested_info": null, "transcript_snippet": "hi"}"""
    parsed = parse_contract(raw, IvrClassificationResponse)
    assert parsed.category == "menu"


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


def test_voice_response_envelope_includes_ssml_and_boson_payload():
    envelope = build_voice_response(
        "voice-session-1",
        "Please say your account ID and then enter 123456.",
    )

    assert envelope is not None
    assert envelope["text"] == "Please say your account ID and then enter 123456."
    assert "account number" in envelope["spoken_text"]
    assert "1 2 3 4 5 6" in envelope["spoken_text"]
    assert envelope["ssml"] == build_ssml(envelope["text"])
    assert envelope["boson"]["type"] == "assistant_output"
    assert envelope["boson"]["session_id"] == "voice-session-1"
    assert envelope["boson"]["text"] == envelope["spoken_text"]


def test_spoken_text_realizer_handles_dates_and_identifiers():
    spoken = realize_spoken_text(
        "Order ORD-123456 shipped on 03/18/2026 and is scheduled to arrive on 03/22/2026. "
        "The carrier is UPS, and the tracking number is 1Z999AA10123456784.",
    )

    assert "Order O R D dash 1 2 3 4 5 6" in spoken
    assert "March 18, 2026" in spoken
    assert "March 22, 2026" in spoken
    assert "U P S" in spoken
    assert "tracking number is 1 Z 9 9 9 A A 1 0 1 2 3 4 5 6 7 8 4" in spoken


def test_voice_response_falls_back_to_canonical_text_on_realizer_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tts_mod, "realize_spoken_text", lambda text: (_ for _ in ()).throw(RuntimeError("boom")))

    envelope = build_voice_response("voice-session-2", "Please continue.")

    assert envelope is not None
    assert envelope["spoken_text"] == "Please continue."
    assert "Please continue." in envelope["ssml"]
    assert envelope["boson"]["text"] == "Please continue."


# --- DTMF flag guardrails (DEV-14) ---

DTMF_COMPATIBLE_VALIDATORS = frozenset({
    "account_number",
    "verification_code",
    "zip_code",
    "order_number",
    "phone",
})

DTMF_INCOMPATIBLE_VALIDATORS = frozenset({
    "non_empty",
    "date",
    "currency",
    "email",
    "yes_no",
    "profile_field",
})


def _all_fields():
    """Yield (intent, field) for every field across all workflow schemas."""
    for intent in list_intents():
        workflow = get_workflow(intent)
        for field in workflow.required_fields + workflow.optional_fields:
            yield intent, field


@pytest.mark.parametrize(
    "intent,field",
    [
        pytest.param(intent, field, id=f"{intent}.{field.name}")
        for intent, field in _all_fields()
        if field.validator in DTMF_COMPATIBLE_VALIDATORS
    ],
)
def test_dtmf_compatible_fields_have_flag_enabled(intent, field):
    """Fields with numeric/ID validators must allow DTMF entry."""
    assert field.dtmf_allowed is True, (
        f"{intent}.{field.name} uses validator '{field.validator}' "
        f"(DTMF-compatible) but has dtmf_allowed=False"
    )


@pytest.mark.parametrize(
    "intent,field",
    [
        pytest.param(intent, field, id=f"{intent}.{field.name}")
        for intent, field in _all_fields()
        if field.validator in DTMF_INCOMPATIBLE_VALIDATORS
    ],
)
def test_dtmf_incompatible_fields_have_flag_disabled(intent, field):
    """Fields with text/date/currency validators must not allow DTMF entry."""
    assert field.dtmf_allowed is False, (
        f"{intent}.{field.name} uses validator '{field.validator}' "
        f"(DTMF-incompatible) but has dtmf_allowed=True"
    )


def test_every_validator_is_classified():
    """Every validator used in schemas must appear in one of the two DTMF sets.

    Forces a conscious decision when a new validator type is introduced.
    """
    classified = DTMF_COMPATIBLE_VALIDATORS | DTMF_INCOMPATIBLE_VALIDATORS
    unclassified = []
    for intent, field in _all_fields():
        if field.validator not in classified:
            unclassified.append(f"{intent}.{field.name} ({field.validator})")
    assert not unclassified, (
        f"Unclassified validator(s) — add to DTMF_COMPATIBLE or "
        f"DTMF_INCOMPATIBLE: {unclassified}"
    )
