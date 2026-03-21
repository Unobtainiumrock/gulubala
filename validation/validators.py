"""Layer 4: deterministic field validators and schema-driven validator lookup."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Callable

from contracts.models import ValidatorSpec

ValidatorFn = Callable[[str], tuple[bool, str]]
_DIGIT_WORDS = {
    "zero": "0",
    "oh": "0",
    "o": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
}


def parse_numeric(value: str | int | float | None) -> float | None:
    """Normalize strings like '$49.99' into comparable numeric values."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    cleaned = str(value).strip().replace(",", "")
    cleaned = cleaned.lstrip("$")
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_digit_tokens(value: str) -> str:
    """Normalize spaced digits or spoken digit words into a compact numeric string."""
    tokens = re.findall(r"[A-Za-z]+|\d+", str(value).lower())
    digits = []
    for token in tokens:
        if token.isdigit():
            digits.append(token)
        elif token in _DIGIT_WORDS:
            digits.append(_DIGIT_WORDS[token])
    return "".join(digits)


def validate_account_number(value: str) -> tuple[bool, str]:
    cleaned = normalize_digit_tokens(value)
    if re.fullmatch(r"\d{8,12}", cleaned):
        return True, cleaned
    return False, "Account number should be 8 to 12 digits."


def validate_verification_code(value: str) -> tuple[bool, str]:
    cleaned = normalize_digit_tokens(value)
    if re.fullmatch(r"\d{6}", cleaned):
        return True, cleaned
    return False, "Verification code should be exactly 6 digits."


def validate_order_number(value: str) -> tuple[bool, str]:
    cleaned = value.strip().upper()
    if re.fullmatch(r"[A-Z0-9\-]{6,20}", cleaned):
        return True, cleaned
    return False, "Order number should be 6 to 20 letters, numbers, or dashes."


def validate_non_empty(value: str) -> tuple[bool, str]:
    if value and value.strip():
        return True, value.strip()
    return False, "This field cannot be empty."


def validate_currency(value: str) -> tuple[bool, str]:
    numeric = parse_numeric(value)
    if numeric is not None:
        return True, f"${numeric:.2f}"
    return False, "Please provide a valid dollar amount, such as $49.99."


def validate_date(value: str) -> tuple[bool, str]:
    cleaned = value.strip()
    formats = [
        "%m/%d/%Y",
        "%m/%d/%y",
        "%m-%d-%Y",
        "%m-%d-%y",
        "%Y-%m-%d",
        "%b %d %Y",
        "%B %d %Y",
        "%b %d, %Y",
        "%B %d, %Y",
    ]
    for fmt in formats:
        try:
            normalized = datetime.strptime(cleaned, fmt).date().isoformat()
            return True, normalized
        except ValueError:
            continue
    return False, "Please provide a date like 03/15/2026 or March 15, 2026."


def validate_email(value: str) -> tuple[bool, str]:
    cleaned = value.strip().lower()
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", cleaned):
        return True, cleaned
    return False, "Please provide a valid email address."


def validate_phone(value: str) -> tuple[bool, str]:
    digits = normalize_digit_tokens(value)
    if 10 <= len(digits) <= 15:
        return True, digits
    return False, "Please provide a valid phone number."


def validate_yes_no(value: str) -> tuple[bool, str]:
    cleaned = value.strip().lower()
    if cleaned in ("yes", "y", "yeah", "yep", "correct", "right", "affirmative"):
        return True, "yes"
    if cleaned in ("no", "n", "nah", "nope", "negative"):
        return True, "no"
    return False, "Please say yes or no."


def validate_profile_field(value: str) -> tuple[bool, str]:
    cleaned = value.strip().lower()
    for field in ("address", "phone", "email", "name"):
        if field in cleaned:
            return True, field
    return False, "Please specify address, phone, email, or name."


def validate_zip_code(value: str) -> tuple[bool, str]:
    cleaned = normalize_digit_tokens(value)
    if re.fullmatch(r"\d{5}", cleaned):
        return True, cleaned
    return False, "Please provide a 5-digit ZIP code."


def _regex_validator(pattern: str, error_message: str) -> ValidatorFn:
    def validate(value: str) -> tuple[bool, str]:
        cleaned = value.strip()
        if re.fullmatch(pattern, cleaned):
            return True, cleaned
        return False, error_message

    return validate


def _enum_validator(values: list[str]) -> ValidatorFn:
    valid_values = {item.lower(): item for item in values}

    def validate(value: str) -> tuple[bool, str]:
        cleaned = value.strip().lower()
        if cleaned in valid_values:
            return True, valid_values[cleaned]
        return False, f"Please provide one of: {', '.join(values)}."

    return validate


_VALIDATORS: dict[str, ValidatorFn] = {
    "account_number": validate_account_number,
    "verification_code": validate_verification_code,
    "order_number": validate_order_number,
    "non_empty": validate_non_empty,
    "currency": validate_currency,
    "date": validate_date,
    "email": validate_email,
    "phone": validate_phone,
    "yes_no": validate_yes_no,
    "profile_field": validate_profile_field,
    "zip_code": validate_zip_code,
}


def get_validator(name: str, spec: ValidatorSpec | None = None) -> ValidatorFn:
    """Look up a validator function by name or a schema-level validator spec."""
    if name in _VALIDATORS:
        return _VALIDATORS[name]

    if spec is None:
        return validate_non_empty

    if spec.type == "regex" and spec.pattern:
        return _regex_validator(spec.pattern, "That value does not match the expected format.")
    if spec.type == "enum" and spec.values:
        return _enum_validator(spec.values)
    if spec.type == "builtin" and spec.name:
        return _VALIDATORS.get(spec.name, validate_non_empty)
    if spec.type in {"text", "enum_text"}:
        return validate_non_empty
    if spec.type == "currency":
        return validate_currency
    if spec.type == "date":
        return validate_date
    if spec.type == "email":
        return validate_email
    if spec.type == "phone":
        return validate_phone
    if spec.type == "yes_no":
        return validate_yes_no

    return validate_non_empty
