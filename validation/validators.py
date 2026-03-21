"""Layer 4: Field validators — regex, type checks, and lookup stubs."""

import re


def validate_account_number(value: str) -> tuple[bool, str]:
    if re.match(r"^[0-9]{8,12}$", value.strip()):
        return True, value.strip()
    return False, "Account number should be 8 to 12 digits."


def validate_verification_code(value: str) -> tuple[bool, str]:
    if re.match(r"^[0-9]{4,8}$", value.strip()):
        return True, value.strip()
    return False, "Verification code should be 4 to 8 digits."


def validate_order_number(value: str) -> tuple[bool, str]:
    cleaned = value.strip().upper()
    if re.match(r"^[A-Z0-9]{6,15}$", cleaned):
        return True, cleaned
    return False, "Order number should be 6 to 15 alphanumeric characters."


def validate_non_empty(value: str) -> tuple[bool, str]:
    if value and value.strip():
        return True, value.strip()
    return False, "This field cannot be empty."


def validate_currency(value: str) -> tuple[bool, str]:
    cleaned = value.strip().lstrip("$")
    if re.match(r"^[0-9]+(\.[0-9]{1,2})?$", cleaned):
        return True, f"${cleaned}"
    return False, "Please provide a valid dollar amount (e.g., $49.99)."


def validate_date(value: str) -> tuple[bool, str]:
    # Accept common date formats loosely
    cleaned = value.strip()
    if re.match(r"^\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}$", cleaned):
        return True, cleaned
    if re.match(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2},?\s*\d{2,4}$", cleaned, re.IGNORECASE):
        return True, cleaned
    return False, "Please provide a date like MM/DD/YYYY or March 15, 2026."


def validate_email(value: str) -> tuple[bool, str]:
    cleaned = value.strip().lower()
    if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", cleaned):
        return True, cleaned
    return False, "Please provide a valid email address."


def validate_phone(value: str) -> tuple[bool, str]:
    digits = re.sub(r"[^\d]", "", value)
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
    return False, "Please specify: address, phone number, or email."


# Validator registry
_VALIDATORS = {
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
}


def get_validator(name: str):
    """Look up a validator function by name."""
    return _VALIDATORS.get(name, validate_non_empty)
