"""Deterministic demo overrides so presenter gather + human bridge always fire.

The scripted ``cancel_service`` IVR asks for a cancel reason (not in CRM) and ends
with a live retention specialist. LLM decide steps are flaky under rate limits;
these rules match the known script lines so Twilio still calls
``PRESENTER_PHONE_NUMBER`` and runs the conference bridge for audiences.
"""

from __future__ import annotations

from contracts.prompts import IvrActionResponse


def apply_demo_human_flow_overrides(
    *,
    enabled: bool,
    transcript_text: str,
    classification_category: str,
    available_fields: dict[str, str],
    escalated: bool,
    action: IvrActionResponse,
) -> IvrActionResponse:
    """If *enabled*, replace LLM action when the script hits presenter or bridge beats."""
    if not enabled or escalated:
        return action

    t = transcript_text.lower()
    af = available_fields

    # Retention "human" beat — last line of scripted cancel_service demo
    if classification_category == "human_agent" or "alex from acme" in t:
        return IvrActionResponse(
            action="escalate",
            escalation_reason=(
                "Demo: live retention specialist on the line — bridge presenter "
                "with the IVR leg."
            ),
            reasoning="Demo override: detected human retention agent.",
        )

    # Open-ended cancel reason — CRM omits cancellation_reason on purpose
    if "cancellation_reason" not in af and (
        "main reason" in t and "cancel" in t
        or "reason you would like to cancel" in t
    ):
        return IvrActionResponse(
            action="request_info",
            requested_field="cancellation_reason",
            field_prompt=(
                "The IVR asked why the customer wants to cancel. "
                "Reply with one short phrase the agent should say."
            ),
            reasoning="Demo override: missing cancellation_reason; calling presenter.",
        )

    return action
