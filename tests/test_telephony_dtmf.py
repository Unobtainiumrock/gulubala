"""Coverage for safe DTMF TwiML generation."""

from __future__ import annotations

import pytest

from telephony import twilio_client


class TestValidateDtmfDigits:
    def test_accepts_valid_sequences(self) -> None:
        assert twilio_client._validate_dtmf_digits("12") == "12"
        assert twilio_client._validate_dtmf_digits(" 9*w# ") == "9*w#"

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            twilio_client._validate_dtmf_digits("")

    def test_rejects_xml_or_injection_chars(self) -> None:
        with pytest.raises(ValueError, match="only contain"):
            twilio_client._validate_dtmf_digits('1"><foo')
