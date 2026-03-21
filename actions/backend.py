"""Layer 5: Backend action stubs — execute tools when all fields are collected."""


def reset_password(fields: dict) -> str:
    account_id = fields.get("account_id", "unknown")
    return (
        f"You're all set. I started a password reset for account {account_id}, "
        "and the reset instructions have been sent to the registered email address."
    )


def open_dispute_case(fields: dict) -> str:
    account = fields.get("account_number", "unknown")
    amount = fields.get("charge_amount", "unknown")
    return (
        f"Your dispute has been opened for account {account} for {amount}. "
        f"Case ID: DSP-{account[-4:] if len(account) >= 4 else '0000'}."
    )


def update_profile(fields: dict) -> str:
    field = fields.get("field_to_update", "unknown")
    new_val = fields.get("new_value", "unknown")
    return f"Your profile has been updated. {field.capitalize()} is now set to {new_val}."


def lookup_order_status(fields: dict) -> str:
    order = fields.get("order_number", "unknown")
    return (
        f"Order {order} shipped on 03/18/2026 and is scheduled to arrive on 03/22/2026. "
        "The carrier is UPS, and the tracking number is 1Z999AA10123456784."
    )


def cancel_subscription(fields: dict) -> str:
    account = fields.get("account_number", "unknown")
    confirm = fields.get("confirm_cancel", "no")
    if confirm == "yes":
        return (
            f"Your subscription for account {account} has been cancelled successfully. "
            "A final billing statement will be sent within 5 business days."
        )
    return "The cancellation was not confirmed, so your service will remain active."


# Action dispatcher
_ACTIONS = {
    "reset_password": reset_password,
    "open_dispute_case": open_dispute_case,
    "update_profile": update_profile,
    "lookup_order_status": lookup_order_status,
    "cancel_subscription": cancel_subscription,
}


def execute_action(action_name: str, fields: dict) -> str:
    """Dispatch to the correct backend action."""
    action_fn = _ACTIONS.get(action_name)
    if action_fn is None:
        return f"Error: unknown action '{action_name}'"
    return action_fn(fields)
