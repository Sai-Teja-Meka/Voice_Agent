"""
Webhook Routes — /api/webhook/*
================================
Receives VAPI webhook events for call logging and monitoring.
"""

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/webhook", tags=["webhooks"])


@router.post("/vapi")
async def vapi_webhook(request: Request):
    """Process VAPI call lifecycle events."""
    body = await request.json()
    event_type = body.get("message", {}).get("type", "unknown")
    print(f"[Aria Webhook] {event_type}")

    if event_type == "end-of-call-report":
        report = body.get("message", {})
        print(f"  Duration: {report.get('duration', '?')}s | Cost: ${report.get('cost', '?')}")
        summary = report.get("summary", "")
        if summary:
            print(f"  Summary: {summary[:200]}")

    return {"status": "ok"}
