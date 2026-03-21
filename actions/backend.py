"""Layer 5: Backend action stubs — execute tools when all fields are collected."""


def reset_password(fields: dict) -> str:
    account_id = fields.get("account_id", "unknown")
    return f"Password reset initiated for account {account_id}. Reset instructions sent to registered email."


def open_dispute_case(fields: dict) -> str:
    account = fields.get("account_number", "unknown")
    amount = fields.get("charge_amount", "unknown")
    return f"Dispute case opened for account {account}, charge amount {amount}. Case ID: DSP-{account[-4:] if len(account) >= 4 else '0000'}."


def update_profile(fields: dict) -> str:
    field = fields.get("field_to_update", "unknown")
    new_val = fields.get("new_value", "unknown")
    return f"Profile updated: {field} changed to {new_val}."


def lookup_order_status(fields: dict) -> str:
    order = fields.get("order_number", "unknown")
    return f"Order {order}: shipped on 03/18/2026, estimated delivery 03/22/2026. Carrier: UPS, tracking #1Z999AA10123456784."


def cancel_subscription(fields: dict) -> str:
    account = fields.get("account_number", "unknown")
    confirm = fields.get("confirm_cancel", "no")
    if confirm == "yes":
        return f"Service cancelled for account {account}. Final billing statement will be sent within 5 business days."
    return "Cancellation not confirmed. Your service remains active."


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
