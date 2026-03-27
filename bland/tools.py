"""Bland AI custom tool schemas for send_call()."""

from __future__ import annotations


def build_start_session_tool(webhook_base_url: str) -> dict:
    """Tool called once at call start to create a session and get the opening line."""
    return {
        "name": "start_session",
        "description": (
            "Initialize the call session. "
            "Call this first before handling any business responses."
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
                "context": "Say this to the business representative.",
            },
        ],
    }


def build_business_turn_tool(webhook_base_url: str) -> dict:
    """Tool called every time the business representative speaks."""
    return {
        "name": "handle_business_turn",
        "description": (
            "Process what the business representative just said through the workflow engine. "
            "Call this every time they speak to get the appropriate response."
        ),
        "url": f"{webhook_base_url}/bland/tool/handle-business-turn",
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
                "context": "Say this to the business representative exactly.",
            },
            {
                "name": "resolved",
                "data": "$.resolved",
                "context": "If true, the task is complete. Thank them and end the call.",
            },
            {
                "name": "escalated",
                "data": "$.escalated",
                "context": "If true, patch in the user.",
            },
        ],
    }


def build_all_tools(webhook_base_url: str) -> list[dict]:
    """Return all custom tools to pass to Bland AI's send_call()."""
    return [
        build_start_session_tool(webhook_base_url),
        build_business_turn_tool(webhook_base_url),
    ]
