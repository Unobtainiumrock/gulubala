"""Bland AI custom tool schemas for send_call()."""

from __future__ import annotations


def build_start_session_tool(webhook_base_url: str) -> dict:
    """Tool called once at call start to create a session and get the greeting."""
    return {
        "name": "start_session",
        "description": (
            "Initialize a customer service session. "
            "Call this first before handling any customer input."
        ),
        "url": f"{webhook_base_url}/bland/tool/start-session",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "body": {"call_id": "{{call_id}}"},
        "response_data": [
            {
                "name": "session_id",
                "data": "$.session_id",
                "context": "The session ID for this call.",
            },
            {
                "name": "greeting",
                "data": "$.message",
                "context": "Say this greeting to the customer.",
            },
        ],
    }


def build_customer_turn_tool(webhook_base_url: str) -> dict:
    """Tool called every time the customer speaks to get the next response."""
    return {
        "name": "handle_customer_turn",
        "description": (
            "Process what the customer just said through the workflow engine. "
            "Call this every time the customer speaks to get the appropriate response."
        ),
        "url": f"{webhook_base_url}/bland/tool/handle-customer-turn",
        "method": "POST",
        "headers": {"Content-Type": "application/json"},
        "body": {
            "call_id": "{{call_id}}",
            "utterance": "{{input}}",
        },
        "speech": "One moment please.",
        "response_data": [
            {
                "name": "response_text",
                "data": "$.message",
                "context": "Say this to the customer exactly.",
            },
            {
                "name": "resolved",
                "data": "$.resolved",
                "context": "If true, the issue is resolved. Thank the customer and end the call.",
            },
            {
                "name": "escalated",
                "data": "$.escalated",
                "context": "If true, transfer to a human agent.",
            },
        ],
    }


def build_all_tools(webhook_base_url: str) -> list[dict]:
    """Return all custom tools to pass to Bland AI's send_call()."""
    return [
        build_start_session_tool(webhook_base_url),
        build_customer_turn_tool(webhook_base_url),
    ]
