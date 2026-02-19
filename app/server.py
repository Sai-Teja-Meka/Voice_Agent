"""
Vikara Voice Scheduling Agent — API Server
============================================
FastAPI backend that serves as the bridge between VAPI's voice agent
and Google Calendar. VAPI calls our tool endpoints; we handle the 
calendar logic and return structured responses.

Architecture:
  [User Voice] → [VAPI Agent] → [This Server] → [Google Calendar API]
                                      ↓
                              [Conflict Detection]
                              [Event Creation]
                              [Confirmation]
"""

import os
import datetime
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from dateutil import parser as date_parser

from app.calendar_service import calendar_service

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    print("=" * 50)
    print("🎙️  Vikara Voice Scheduling Agent — Online")
    print(f"📅  Calendar Auth: {'✅ Connected' if calendar_service.is_authenticated else '❌ Not connected'}")
    print(f"🌐  Server: {os.getenv('SERVER_URL', 'http://localhost:8000')}")
    print("=" * 50)
    yield
    print("Shutting down...")


app = FastAPI(
    title="Vikara Voice Scheduling Agent",
    description="Real-time voice assistant for scheduling calendar events",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — VAPI needs to reach us
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# Health & Status
# ──────────────────────────────────────────────

@app.get("/")
async def root():
    return HTMLResponse(content="""
    <html>
    <head><title>Vikara Voice Agent</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; background: #0a0a0a; color: #e0e0e0;
               display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        .container { text-align: center; max-width: 600px; padding: 40px; }
        h1 { font-size: 2.5rem; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
             -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .status { margin: 20px 0; padding: 15px; border-radius: 12px; background: #1a1a2e; }
        .badge { display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 0.85rem; }
        .badge.ok { background: #1b4332; color: #95d5b2; }
        .badge.warn { background: #5c3a0d; color: #fbbf24; }
        a { color: #667eea; text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style></head>
    <body>
        <div class="container">
            <h1>🎙️ Voice Scheduling Agent</h1>
            <p>Built for Vikara.ai Assessment</p>
            <div class="status">
                <p>Calendar: """ + (
                    '<span class="badge ok">✅ Connected</span>' if calendar_service.is_authenticated
                    else '<span class="badge warn">⚠️ Not Connected — <a href="/auth/login">Authorize Google Calendar</a></span>'
                ) + """</p>
                <p>API: <span class="badge ok">✅ Online</span></p>
            </div>
            <p style="margin-top: 30px; font-size: 0.9rem; color: #888;">
                <a href="/docs">API Docs</a> · 
                <a href="/health">Health Check</a>
            </p>
        </div>
    </body></html>
    """)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "calendar_connected": calendar_service.is_authenticated,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }


# ──────────────────────────────────────────────
# Google OAuth Flow
# ──────────────────────────────────────────────

@app.get("/auth/login")
async def auth_login():
    """Redirect user to Google OAuth consent screen."""
    auth_url = calendar_service.get_auth_url()
    return RedirectResponse(url=auth_url)


@app.get("/auth/callback")
async def auth_callback(code: str = Query(...)):
    """Handle Google OAuth callback."""
    success = calendar_service.handle_callback(code)
    if success:
        return HTMLResponse(content="""
        <html><body style="font-family: sans-serif; text-align: center; padding: 60px; background: #0a0a0a; color: #e0e0e0;">
            <h1>✅ Google Calendar Connected!</h1>
            <p>The voice agent can now create calendar events.</p>
            <p><a href="/" style="color: #667eea;">← Back to Dashboard</a></p>
        </body></html>
        """)
    return HTMLResponse(content="<h1>❌ Authentication failed. Please try again.</h1>", status_code=400)


# ──────────────────────────────────────────────
# VAPI Tool Endpoints (Server URL Tools)
# ──────────────────────────────────────────────

class ScheduleEventRequest(BaseModel):
    """Schema for the schedule_event tool call from VAPI."""
    name: str
    date: str  # e.g., "2026-02-20" or "tomorrow" or "February 20th"
    time: str  # e.g., "3:00 PM" or "15:00"
    title: Optional[str] = None
    duration_minutes: Optional[int] = 30


class CheckConflictRequest(BaseModel):
    """Schema for conflict checking."""
    date: str
    time: str
    duration_minutes: Optional[int] = 30


def parse_datetime(date_str: str, time_str: str) -> datetime.datetime:
    """
    Parse natural language date/time into a datetime object.
    Handles formats like 'tomorrow', 'February 20th', '3pm', '15:00', etc.
    """
    from dateutil import tz as dateutil_tz
    
    # Handle relative dates explicitly
    today = datetime.datetime.now()
    date_lower = date_str.strip().lower()
    
    if date_lower == "today":
        base_date = today
    elif date_lower == "tomorrow":
        base_date = today + datetime.timedelta(days=1)
    else:
        # Parse the date string
        try:
            base_date = date_parser.parse(date_str, fuzzy=True)
            # If parsed date is in the past (same year), push to NEXT occurrence
            # but DON'T blindly add a year — check if it's a same-year date
            if base_date.date() < today.date():
                # Try next year only if the month/day combo is past
                candidate = base_date.replace(year=today.year)
                if candidate.date() < today.date():
                    candidate = base_date.replace(year=today.year + 1)
                base_date = candidate
        except Exception:
            base_date = today  # fallback

    # Parse the time string
    try:
        time_part = date_parser.parse(time_str, fuzzy=True)
        result = base_date.replace(
            hour=time_part.hour, minute=time_part.minute, second=0, microsecond=0
        )
    except Exception:
        # If time parsing fails, try combining
        try:
            combined = f"{date_str} {time_str}"
            result = date_parser.parse(combined, fuzzy=True)
        except Exception as e:
            raise ValueError(f"Could not parse date/time: '{date_str} {time_str}'. Error: {e}")

    # Attach timezone (default Eastern)
    target_tz = dateutil_tz.gettz("America/New_York")
    if result.tzinfo is None:
        result = result.replace(tzinfo=target_tz)
    
    return result


@app.post("/api/tool/schedule-event")
async def tool_schedule_event(request: Request):
    """
    VAPI Server URL Tool — Schedule a calendar event.
    
    VAPI sends tool calls to this endpoint. We parse the arguments,
    create the Google Calendar event, and return a result that the 
    voice agent speaks back to the user.
    """
    body = await request.json()
    
    # VAPI sends the tool call in a specific format
    # Extract the function arguments
    tool_call = _extract_tool_call(body)
    if not tool_call:
        return JSONResponse(content={"error": "Invalid tool call format"}, status_code=400)

    args = tool_call.get("function", {}).get("arguments", {})
    
    name = args.get("name", "Guest")
    date_str = args.get("date", "")
    time_str = args.get("time", "")
    title = args.get("title", None)
    duration = int(args.get("duration_minutes", 30))

    # Check calendar authentication
    if not calendar_service.is_authenticated:
        return _vapi_tool_response(
            tool_call_id=tool_call.get("id", ""),
            result="I'm sorry, the calendar isn't connected yet. Please ask the administrator to authorize Google Calendar first."
        )

    # Parse the datetime
    try:
        start_time = parse_datetime(date_str, time_str)
        end_time = start_time + datetime.timedelta(minutes=duration)
    except ValueError as e:
        return _vapi_tool_response(
            tool_call_id=tool_call.get("id", ""),
            result=f"I couldn't understand the date or time. Could you please repeat that? Error: {str(e)}"
        )

    # Check for conflicts
    conflicts = calendar_service.check_conflicts(start_time, end_time)
    if conflicts:
        conflict_names = [e.get("summary", "Busy") for e in conflicts]
        return _vapi_tool_response(
            tool_call_id=tool_call.get("id", ""),
            result=f"There's a conflict — you already have '{conflict_names[0]}' at that time. Would you like to pick a different time?"
        )

    # Create the event
    try:
        event = calendar_service.create_event(
            summary=title or f"Meeting with {name}",
            start_time=start_time,
            end_time=end_time,
            attendee_name=name,
            description=f"Scheduled by {name} via Vikara Voice Agent",
        )
        
        formatted_date = start_time.strftime("%A, %B %d at %I:%M %p")
        return _vapi_tool_response(
            tool_call_id=tool_call.get("id", ""),
            result=f"I've successfully created the event '{event['summary']}' for {formatted_date}. The event is confirmed on your Google Calendar. Is there anything else I can help you with?"
        )
    except Exception as e:
        return _vapi_tool_response(
            tool_call_id=tool_call.get("id", ""),
            result=f"I encountered an error creating the event: {str(e)}. Please try again."
        )


@app.post("/api/tool/check-availability")
async def tool_check_availability(request: Request):
    """
    VAPI Server URL Tool — Check calendar availability.
    The agent can proactively check if a time slot is free.
    """
    body = await request.json()
    tool_call = _extract_tool_call(body)
    if not tool_call:
        return JSONResponse(content={"error": "Invalid tool call format"}, status_code=400)

    args = tool_call.get("function", {}).get("arguments", {})
    date_str = args.get("date", "")
    time_str = args.get("time", "")
    duration = int(args.get("duration_minutes", 30))

    if not calendar_service.is_authenticated:
        return _vapi_tool_response(
            tool_call_id=tool_call.get("id", ""),
            result="Calendar not connected. Unable to check availability."
        )

    try:
        start_time = parse_datetime(date_str, time_str)
        end_time = start_time + datetime.timedelta(minutes=duration)
        conflicts = calendar_service.check_conflicts(start_time, end_time)
        
        if conflicts:
            return _vapi_tool_response(
                tool_call_id=tool_call.get("id", ""),
                result=f"That time slot is not available. There's an existing event: '{conflicts[0].get('summary', 'Busy')}'. Would you like to try a different time?"
            )
        
        formatted = start_time.strftime("%A, %B %d at %I:%M %p")
        return _vapi_tool_response(
            tool_call_id=tool_call.get("id", ""),
            result=f"Great news! {formatted} is available. Shall I go ahead and book it?"
        )
    except ValueError as e:
        return _vapi_tool_response(
            tool_call_id=tool_call.get("id", ""),
            result=f"I couldn't parse that date/time. Could you say it again?"
        )


# ──────────────────────────────────────────────
# VAPI Webhook (optional — for call logging)
# ──────────────────────────────────────────────

@app.post("/api/webhook/vapi")
async def vapi_webhook(request: Request):
    """
    Receives VAPI webhook events for call status updates.
    Useful for logging and monitoring.
    """
    body = await request.json()
    event_type = body.get("message", {}).get("type", "unknown")
    
    print(f"[VAPI Webhook] Event: {event_type}")
    
    if event_type == "end-of-call-report":
        report = body.get("message", {})
        print(f"  Call Duration: {report.get('duration', 'N/A')}s")
        print(f"  Cost: ${report.get('cost', 'N/A')}")
        print(f"  Transcript Summary: {report.get('summary', 'N/A')}")
    
    return {"status": "ok"}


# ──────────────────────────────────────────────
# Helper Functions
# ──────────────────────────────────────────────

def _extract_tool_call(body: dict) -> Optional[dict]:
    """
    Extract tool call from VAPI's request format.
    VAPI sends tool calls in the message payload.
    """
    message = body.get("message", {})
    
    # VAPI server-url tool call format
    tool_calls = message.get("toolCalls", [])
    if tool_calls:
        return tool_calls[0]
    
    # Alternative: direct tool call in body
    if "toolCall" in message:
        return message["toolCall"]
    
    # Fallback: check if the body itself is a tool call
    if "function" in body:
        return body
    
    return None


def _vapi_tool_response(tool_call_id: str, result: str) -> JSONResponse:
    """Format response in VAPI's expected tool result format."""
    return JSONResponse(content={
        "results": [
            {
                "toolCallId": tool_call_id,
                "result": result,
            }
        ]
    })


# ──────────────────────────────────────────────
# Direct API (for testing without VAPI)
# ──────────────────────────────────────────────

@app.post("/api/direct/schedule")
async def direct_schedule(req: ScheduleEventRequest):
    """
    Direct endpoint for testing calendar integration without VAPI.
    Call this from Postman/curl to verify events get created.
    """
    if not calendar_service.is_authenticated:
        return JSONResponse(
            content={"error": "Not authenticated. Visit /auth/login first."},
            status_code=401,
        )

    try:
        start_time = parse_datetime(req.date, req.time)
        end_time = start_time + datetime.timedelta(minutes=req.duration_minutes)
    except ValueError as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)

    # Check conflicts
    conflicts = calendar_service.check_conflicts(start_time, end_time)
    if conflicts:
        return JSONResponse(content={
            "status": "conflict",
            "conflicts": [{"summary": e.get("summary"), "start": e.get("start")} for e in conflicts],
            "message": "Time slot has conflicts. Choose another time.",
        })

    # Create event
    event = calendar_service.create_event(
        summary=req.title or f"Meeting with {req.name}",
        start_time=start_time,
        end_time=end_time,
        attendee_name=req.name,
    )

    return {"status": "created", "event": event}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app.server:app", host="0.0.0.0", port=port, reload=True)
