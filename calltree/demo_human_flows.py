"""Fully deterministic demo overrides for the scripted cancel_service IVR.

The LLM classify/decide steps are flaky under Eigen 429 rate limits and
sometimes produce wrong actions (premature escalations, truncated JSON).
When ``enabled=True`` (the default for scripted demos), every IVR line is
pattern-matched and the correct action is returned directly — the LLM
action is ignored entirely.  This guarantees:

  1. DTMF navigation through the Acme Corp menus
  2. Account number entry from pre-filled fields
  3. Soft escalation (presenter Gather call) for cancellation_reason
  4. Confirmation spoken from pre-filled fields
  5. Hard escalation (conference bridge) when the retention agent speaks
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
    """If *enabled*, return a deterministic action for every scripted IVR line.

    Falls back to the LLM action only if no pattern matches (shouldn't happen
    for the known cancel_service script).
    """
    if not enabled or escalated:
        return action

    t = transcript_text.lower()
    af = available_fields

    # ── Line 1: root menu ─────────────────────────────────────────────
    # "Press 1 for billing, 2 for account services, or 3 for order support."
    if "billing" in t and "account services" in t:
        return IvrActionResponse(
            action="send_dtmf",
            dtmf_digits="1",
            reasoning="Demo: selecting billing menu to reach cancellation.",
        )

    # ── Line 2: billing sub-menu ──────────────────────────────────────
    # "For a billing dispute, press 1. To cancel your service, press 2."
    if "cancel your service" in t:
        return IvrActionResponse(
            action="send_dtmf",
            dtmf_digits="2",
            reasoning="Demo: selecting cancel service.",
        )

    # ── Line 3: hold / transfer ───────────────────────────────────────
    # "Please hold while I connect you to our cancellation specialist."
    if "please hold" in t or "connect you to" in t:
        return IvrActionResponse(
            action="wait",
            reasoning="Demo: waiting for transfer to complete.",
        )

    # ── Line 4: account number ────────────────────────────────────────
    # "Please say or enter your account number so I can locate the subscription."
    if "account number" in t:
        acct = af.get("account_number", "12345678")
        return IvrActionResponse(
            action="send_dtmf",
            dtmf_digits=acct,
            reasoning=f"Demo: entering account number {acct}.",
        )

    # ── Line 5: cancellation reason (soft escalation) ─────────────────
    # "What is the main reason you would like to cancel today?"
    if ("main reason" in t and "cancel" in t) or "reason you would like to cancel" in t:
        if "cancellation_reason" in af:
            # Already gathered — speak it
            return IvrActionResponse(
                action="speak",
                speech_text=af["cancellation_reason"],
                reasoning="Demo: speaking previously gathered cancellation reason.",
            )
        return IvrActionResponse(
            action="request_info",
            requested_field="cancellation_reason",
            field_prompt=(
                "Why is the customer canceling? "
                "For example: switching vendors, too expensive, or no longer needed."
            ),
            reasoning="Demo: missing cancellation_reason; calling presenter.",
        )

    # ── Line 6: confirm cancellation ──────────────────────────────────
    # "Would you like me to cancel the subscription now? Please say yes or no."
    if "cancel" in t and ("yes or no" in t or "say yes" in t):
        confirm = af.get("confirm_cancel", "yes")
        return IvrActionResponse(
            action="speak",
            speech_text=confirm,
            reasoning=f"Demo: confirming cancellation ({confirm}).",
        )

    # ── Line 7: retention agent (hard escalation) ─────────────────────
    # "Hi, this is Alex from Acme retention..."
    if "alex from acme" in t or "retention" in t or classification_category == "human_agent":
        return IvrActionResponse(
            action="escalate",
            escalation_reason=(
                "Demo: live retention specialist on the line — bridge presenter "
                "with the IVR leg."
            ),
            reasoning="Demo: detected human retention agent.",
        )

    # ── Fallback: suppress any LLM escalation, otherwise pass through ─
    if action.action == "escalate":
        return IvrActionResponse(
            action="wait",
            reasoning="Demo: suppressed unexpected escalation; waiting for next prompt.",
        )

    return action
