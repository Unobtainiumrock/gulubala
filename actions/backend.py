"""Layer 5 backend action contracts and stub implementations.

Teammate-facing drop-in replacement contract:

- Signature: ``def action_name(fields: <TypedDict>) -> str``
- Input: ``fields`` is the normalized ``session.validated_fields`` mapping
  from the workflow engine after all required validation has already passed.
- Return: a caller-safe success string that can be shown in the CLI, HTTP API,
  and voice channel.
- Compatibility: success strings should keep a stable leading status phrase
  such as ``"Password reset initiated"``, ``"Dispute case opened"``,
  ``"Profile updated"``, or ``"Service cancelled"`` so downstream tests and
  demo flows can assert behavior without relying on full sentence equality.
- Failure handling: either raise an exception or return a string starting with
  ``"Error:"``. The orchestrator treats both as backend failures and escalates.

Implementations should stay synchronous and accept exactly one positional
argument named ``fields`` so they remain drop-in compatible with
``execute_action``.
"""

from __future__ import annotations

from typing import Callable, NotRequired, TypeAlias, TypedDict


ActionResult: TypeAlias = str


class PasswordResetFields(TypedDict):
    """Validated input shape for ``reset_password``.

    Required keys:
    - ``account_id``: normalized account number string
    - ``verification_code``: normalized verification code string

    Optional keys:
    - ``callback_number``: normalized caller callback number if collected
    """

    account_id: str
    verification_code: str
    callback_number: NotRequired[str]


class BillingDisputeFields(TypedDict):
    """Validated input shape for ``open_dispute_case``."""

    account_number: str
    charge_date: str
    charge_amount: str
    dispute_reason: str
    merchant_name: NotRequired[str]
    reference_number: NotRequired[str]


class UpdateProfileFields(TypedDict):
    """Validated input shape for ``update_profile``."""

    account_number: str
    field_to_update: str
    new_value: str


class OrderStatusFields(TypedDict):
    """Validated input shape for ``lookup_order_status``."""

    order_number: str
    zip_code: NotRequired[str]
    email: NotRequired[str]


class CancelSubscriptionFields(TypedDict):
    """Validated input shape for ``cancel_subscription``.

    Required keys:
    - ``account_number``: normalized account number string
    - ``cancellation_reason``: free-text reason supplied by the caller
    - ``confirm_cancel``: normalized yes/no string, expected to be ``"yes"``
      or ``"no"``
    """

    account_number: str
    cancellation_reason: str
    confirm_cancel: str


ActionHandler: TypeAlias = Callable[[dict[str, str]], ActionResult]


def reset_password(fields: PasswordResetFields) -> ActionResult:
    """Reset a password using validated password-reset workflow fields.

    Drop-in replacement signature:
    ``def reset_password(fields: PasswordResetFields) -> str``

    Expected input dict shape:
    - required: ``account_id``, ``verification_code``
    - optional: ``callback_number``

    Expected return:
    - success: user-facing confirmation string
    - failure: raise an exception or return ``"Error: ..."``
    """
    account_id = fields.get("account_id", "unknown")
    callback_number = fields.get("callback_number")
    callback_note = (
        f" If we need to follow up, we will call {callback_number}."
        if callback_number
        else ""
    )
    return (
        f"Password reset initiated. You're all set. I started a password reset for account {account_id}, "
        "and the reset instructions have been sent to the registered email address."
        f"{callback_note}"
    )


def open_dispute_case(fields: BillingDisputeFields) -> ActionResult:
    """Open a billing dispute case from validated dispute workflow fields."""
    account = fields.get("account_number", "unknown")
    amount = fields.get("charge_amount", "unknown")
    charge_date = fields.get("charge_date", "unknown date")
    dispute_reason = fields.get("dispute_reason", "unspecified reason")
    return (
        f"Dispute case opened. Your dispute has been opened for account {account} "
        f"for {amount} from {charge_date}. Reason noted: {dispute_reason}. "
        f"Case ID: DSP-{account[-4:] if len(account) >= 4 else '0000'}."
    )


def update_profile(fields: UpdateProfileFields) -> ActionResult:
    """Update a profile field from validated update-profile workflow fields."""
    field = fields.get("field_to_update", "unknown").replace("_", " ")
    new_val = fields.get("new_value", "unknown")
    return f"Profile updated. Your profile has been updated. {field.capitalize()} is now set to {new_val}."


def lookup_order_status(fields: OrderStatusFields) -> ActionResult:
    """Look up order status from validated order-status workflow fields."""
    order = fields.get("order_number", "unknown")
    return (
        f"Order {order} shipped on 03/18/2026 and is scheduled to arrive on 03/22/2026. "
        "The carrier is UPS, and the tracking number is 1Z999AA10123456784."
    )


def cancel_subscription(fields: CancelSubscriptionFields) -> ActionResult:
    """Cancel a subscription using validated cancel-service workflow fields.

    Drop-in replacement signature:
    ``def cancel_subscription(fields: CancelSubscriptionFields) -> str``

    Expected input dict shape:
    - required: ``account_number``, ``cancellation_reason``, ``confirm_cancel``
    - ``confirm_cancel`` is normalized before this function runs and should be
      either ``"yes"`` or ``"no"``

    Expected return:
    - success: user-facing confirmation string
    - failure: raise an exception or return ``"Error: ..."``
    """
    account = fields.get("account_number", "unknown")
    reason = fields.get("cancellation_reason", "unspecified reason")
    confirm = fields.get("confirm_cancel", "no")
    if confirm == "yes":
        return (
            f"Service cancelled. Your subscription for account {account} has been cancelled successfully. "
            f"We noted the reason as {reason}. "
            "A final billing statement will be sent within 5 business days."
        )
    return (
        f"Cancellation not confirmed. Your service remains active for account {account}, "
        "and no changes were made."
    )


# Action dispatcher
_ACTIONS: dict[str, ActionHandler] = {
    "reset_password": reset_password,
    "open_dispute_case": open_dispute_case,
    "update_profile": update_profile,
    "lookup_order_status": lookup_order_status,
    "cancel_subscription": cancel_subscription,
}


def execute_action(action_name: str, fields: dict[str, str]) -> ActionResult:
    """Dispatch to the correct backend action.

    ``fields`` is always the normalized validated field mapping for the active
    workflow. Unknown actions return ``"Error: ..."`` so callers can treat that
    as a backend failure without special-case handling.
    """
    action_fn = _ACTIONS.get(action_name)
    if action_fn is None:
        return f"Error: unknown action '{action_name}'"
    return action_fn(fields)
