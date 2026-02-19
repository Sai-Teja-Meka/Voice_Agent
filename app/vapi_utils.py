"""
VAPI Utilities
===============
Helpers for extracting tool calls from VAPI payloads
and formatting responses in VAPI's expected contract.
"""

from typing import Optional
from fastapi.responses import JSONResponse


def extract_tool_call(body: dict) -> Optional[dict]:
    """
    Extract tool call from VAPI's request payload.
    Handles multiple VAPI payload formats.
    """
    message = body.get("message", {})

    # Server-url tool call format
    tool_calls = message.get("toolCalls", [])
    if tool_calls:
        return tool_calls[0]

    # Alternative format
    if "toolCall" in message:
        return message["toolCall"]

    # Direct tool call in body
    if "function" in body:
        return body

    return None


def tool_response(tool_call_id: str, result: str) -> JSONResponse:
    """Format response in VAPI's expected tool result contract."""
    return JSONResponse(content={
        "results": [{"toolCallId": tool_call_id, "result": result}]
    })
