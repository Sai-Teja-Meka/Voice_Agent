"""
Aria — Voice Scheduling Agent API Server
==========================================
FastAPI backend powering Aria, the voice scheduling assistant.

Architecture:
  [User Voice] → [VAPI/Aria] → [This Server] → [Google Calendar API]
                                      ↓
                              [Conflict Detection]
                              [Availability Slots]
                              [Event Creation]
                              [SQLite Booking Log]
"""

import os
import json
import sqlite3
import datetime
import traceback
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
from dateutil import parser as date_parser
from dateutil import tz as dateutil_tz

from app.calendar_service import calendar_service

load_dotenv()

# ──────────────────────────────────────────────
# SQLite Booking Log
# ──────────────────────────────────────────────

DB_PATH = "bookings.db"


def init_db():
    """Initialize the SQLite booking log."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            caller_name TEXT NOT NULL,
            meeting_title TEXT,
            scheduled_date TEXT NOT NULL,
            scheduled_time TEXT NOT NULL,
            duration_minutes INTEGER DEFAULT 30,
            timezone TEXT DEFAULT 'America/New_York',
            google_event_id TEXT,
            google_event_link TEXT,
            status TEXT DEFAULT 'confirmed',
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def log_booking(
    caller_name: str,
    meeting_title: str,
    scheduled_date: str,
    scheduled_time: str,
    duration_minutes: int,
    timezone: str,
    google_event_id: str,
    google_event_link: str,
):
    """Log a successful booking to SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO bookings 
           (caller_name, meeting_title, scheduled_date, scheduled_time, 
            duration_minutes, timezone, google_event_id, google_event_link, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            caller_name,
            meeting_title,
            scheduled_date,
            scheduled_time,
            duration_minutes,
            timezone,
            google_event_id,
            google_event_link,
            datetime.datetime.now(datetime.timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def get_recent_bookings(limit: int = 20) -> list[dict]:
    """Fetch recent bookings for the dashboard."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM bookings ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ──────────────────────────────────────────────
# App Lifecycle
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print("=" * 55)
    print("  🎙️  Aria — Voice Scheduling Agent")
    print(f"  📅  Calendar: {'✅ Connected' if calendar_service.is_authenticated else '❌ Not connected'}")
    print(f"  🌐  Server: {os.getenv('SERVER_URL', 'http://localhost:8000')}")
    print(f"  📊  Booking DB: {DB_PATH}")
    print("=" * 55)
    yield
    print("Shutting down Aria...")


app = FastAPI(
    title="Aria — Voice Scheduling Agent",
    description="Real-time voice assistant for intelligent calendar scheduling",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# Landing Page & Dashboard
# ──────────────────────────────────────────────

@app.get("/")
async def landing_page():
    """Branded landing page with embedded VAPI widget."""
    assistant_id = os.getenv("VAPI_ASSISTANT_ID", "")
    vapi_public_key = os.getenv("VAPI_PUBLIC_KEY", "")
    
    return HTMLResponse(content=f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Aria — Voice Scheduling Assistant</title>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            
            body {{
                font-family: 'Inter', -apple-system, sans-serif;
                background: #050505;
                color: #e8e8e8;
                min-height: 100vh;
                overflow-x: hidden;
            }}
            
            /* Ambient gradient background */
            .bg-gradient {{
                position: fixed;
                top: 0; left: 0; right: 0; bottom: 0;
                background: 
                    radial-gradient(ellipse at 20% 50%, rgba(88, 28, 135, 0.15) 0%, transparent 50%),
                    radial-gradient(ellipse at 80% 20%, rgba(15, 82, 186, 0.1) 0%, transparent 50%),
                    radial-gradient(ellipse at 50% 80%, rgba(88, 28, 135, 0.08) 0%, transparent 50%);
                z-index: 0;
            }}
            
            .container {{
                position: relative;
                z-index: 1;
                max-width: 900px;
                margin: 0 auto;
                padding: 60px 24px;
                text-align: center;
            }}
            
            /* Header */
            .logo {{
                font-size: 0.85rem;
                font-weight: 500;
                letter-spacing: 3px;
                text-transform: uppercase;
                color: #8b5cf6;
                margin-bottom: 24px;
            }}
            
            h1 {{
                font-size: 3.2rem;
                font-weight: 700;
                line-height: 1.1;
                margin-bottom: 16px;
                background: linear-gradient(135deg, #e8e8e8 0%, #a78bfa 50%, #7c3aed 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }}
            
            .subtitle {{
                font-size: 1.15rem;
                color: #9ca3af;
                max-width: 500px;
                margin: 0 auto 48px;
                line-height: 1.6;
            }}
            
            /* Call Button */
            .call-section {{
                margin: 40px 0 60px;
            }}
            
            .call-btn {{
                display: inline-flex;
                align-items: center;
                gap: 12px;
                padding: 18px 48px;
                background: linear-gradient(135deg, #7c3aed 0%, #5b21b6 100%);
                color: white;
                border: none;
                border-radius: 60px;
                font-size: 1.1rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s ease;
                box-shadow: 0 0 40px rgba(124, 58, 237, 0.3);
            }}
            
            .call-btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 0 60px rgba(124, 58, 237, 0.5);
            }}
            
            .call-btn:active {{
                transform: translateY(0);
            }}
            
            .call-btn .icon {{
                font-size: 1.3rem;
            }}
            
            .call-btn.active {{
                background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%);
                box-shadow: 0 0 40px rgba(220, 38, 38, 0.3);
                animation: pulse-red 2s infinite;
            }}
            
            @keyframes pulse-red {{
                0%, 100% {{ box-shadow: 0 0 40px rgba(220, 38, 38, 0.3); }}
                50% {{ box-shadow: 0 0 60px rgba(220, 38, 38, 0.5); }}
            }}
            
            .call-status {{
                margin-top: 16px;
                font-size: 0.9rem;
                color: #6b7280;
                min-height: 24px;
            }}
            
            /* Features */
            .features {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 20px;
                margin: 0 0 60px;
                text-align: left;
            }}
            
            .feature {{
                padding: 24px;
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 16px;
                transition: border-color 0.3s;
            }}
            
            .feature:hover {{
                border-color: rgba(124, 58, 237, 0.3);
            }}
            
            .feature .icon {{ font-size: 1.5rem; margin-bottom: 12px; }}
            .feature h3 {{ font-size: 0.95rem; font-weight: 600; margin-bottom: 8px; }}
            .feature p {{ font-size: 0.85rem; color: #6b7280; line-height: 1.5; }}
            
            /* Bookings Feed */
            .bookings-section {{
                text-align: left;
                margin-top: 60px;
            }}
            
            .bookings-section h2 {{
                font-size: 1.3rem;
                font-weight: 600;
                margin-bottom: 20px;
                color: #d1d5db;
            }}
            
            .booking-list {{
                display: flex;
                flex-direction: column;
                gap: 8px;
            }}
            
            .booking-item {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 16px 20px;
                background: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                font-size: 0.9rem;
            }}
            
            .booking-item .name {{ font-weight: 500; color: #e8e8e8; }}
            .booking-item .title {{ color: #8b5cf6; }}
            .booking-item .time {{ color: #6b7280; font-size: 0.85rem; }}
            
            .empty-state {{
                padding: 40px;
                text-align: center;
                color: #4b5563;
                font-size: 0.9rem;
            }}
            
            /* Status Bar */
            .status-bar {{
                margin-top: 60px;
                padding: 16px 24px;
                background: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                display: flex;
                justify-content: center;
                gap: 32px;
                font-size: 0.85rem;
                color: #6b7280;
            }}
            
            .status-item {{ display: flex; align-items: center; gap: 8px; }}
            .status-dot {{ width: 8px; height: 8px; border-radius: 50%; }}
            .status-dot.green {{ background: #22c55e; }}
            .status-dot.yellow {{ background: #eab308; }}
            .status-dot.red {{ background: #ef4444; }}
            
            /* Footer */
            .footer {{
                margin-top: 48px;
                font-size: 0.8rem;
                color: #374151;
            }}
            .footer a {{ color: #6b7280; text-decoration: none; }}
            .footer a:hover {{ color: #8b5cf6; }}
            
            @media (max-width: 768px) {{
                h1 {{ font-size: 2.2rem; }}
                .features {{ grid-template-columns: 1fr; }}
            }}
        </style>
    </head>
    <body>
        <div class="bg-gradient"></div>
        
        <div class="container">
            <div class="logo">Vikara.ai</div>
            <h1>Meet Aria</h1>
            <p class="subtitle">
                Your voice-powered scheduling assistant. Just speak naturally — 
                Aria will find the perfect time and book it on your calendar.
            </p>
            
            <div class="call-section">
                <button id="callBtn" class="call-btn" onclick="toggleCall()">
                    <span class="icon">🎙️</span>
                    <span id="btnText">Talk to Aria</span>
                </button>
                <div id="callStatus" class="call-status"></div>
            </div>
            
            <div class="features">
                <div class="feature">
                    <div class="icon">🧠</div>
                    <h3>Natural Conversation</h3>
                    <p>Powered by Claude — understands "next Tuesday afternoon" or "sometime this week"</p>
                </div>
                <div class="feature">
                    <div class="icon">📅</div>
                    <h3>Smart Scheduling</h3>
                    <p>Checks your calendar for conflicts and suggests available slots automatically</p>
                </div>
                <div class="feature">
                    <div class="icon">⚡</div>
                    <h3>Instant Booking</h3>
                    <p>Creates real Google Calendar events with one conversation — no forms, no clicks</p>
                </div>
            </div>
            
            <div class="bookings-section">
                <h2>📋 Recent Bookings</h2>
                <div id="bookingsList" class="booking-list">
                    <div class="empty-state">No bookings yet — be the first to talk to Aria!</div>
                </div>
            </div>
            
            <div class="status-bar">
                <div class="status-item">
                    <span class="status-dot green"></span>
                    API Online
                </div>
                <div class="status-item">
                    <span id="calDot" class="status-dot {'green' if calendar_service.is_authenticated else 'yellow'}"></span>
                    <span id="calText">Calendar {'Connected' if calendar_service.is_authenticated else 'Not Connected'}</span>
                </div>
                <div class="status-item">
                    <span class="status-dot green"></span>
                    Claude Opus 4.6
                </div>
            </div>
            
            <div class="footer">
                <p>Built by Sai Teja · 
                    <a href="/docs">API Docs</a> · 
                    <a href="/health">Health</a> · 
                    <a href="/api/bookings">Bookings API</a>
                </p>
            </div>
        </div>
        
        <!-- VAPI Web SDK -->
        <script type="module">
            import Vapi from "https://cdn.jsdelivr.net/npm/@vapi-ai/web@latest/+esm";
            window.Vapi = Vapi;
            window.vapiReady = true;
            window.dispatchEvent(new Event('vapiLoaded'));
       </script>
        <script type="module">
    import Vapi from "https://cdn.jsdelivr.net/npm/@vapi-ai/web@latest/+esm";
    
    const publicKey = "{vapi_public_key}";
    const assistantId = "{assistant_id}";
    let vapi = null;
    let isCallActive = false;
    
    if (publicKey && publicKey !== "") {{
        vapi = new Vapi(publicKey);
        
        vapi.on("call-start", () => {{
            isCallActive = true;
            document.getElementById("callBtn").classList.add("active");
            document.getElementById("btnText").textContent = "End Call";
            document.getElementById("callStatus").textContent = "Connected — speak naturally";
        }});
        
        vapi.on("call-end", () => {{
            isCallActive = false;
            document.getElementById("callBtn").classList.remove("active");
            document.getElementById("btnText").textContent = "Talk to Aria";
            document.getElementById("callStatus").textContent = "Call ended";
            loadBookings();
        }});
        
        vapi.on("error", (e) => {{
            console.error("VAPI Error:", e);
            document.getElementById("callStatus").textContent = "Connection error — please try again";
        }});
    }}
    
    window.toggleCall = function() {{
        if (!vapi) {{
            document.getElementById("callStatus").textContent = "Voice widget not configured — test via VAPI Dashboard";
            return;
        }}
        if (isCallActive) {{
            vapi.stop();
        }} else {{
            document.getElementById("callStatus").textContent = "Connecting...";
            vapi.start(assistantId);
        }}
    }};
    
    async function loadBookings() {{
        try {{
            const res = await fetch("/api/bookings");
            const data = await res.json();
            const list = document.getElementById("bookingsList");
            if (data.bookings && data.bookings.length > 0) {{
                list.innerHTML = data.bookings.map(b => `
                    <div class="booking-item">
                        <span class="name">${{b.caller_name}}</span>
                        <span class="title">${{b.meeting_title || 'Meeting'}}</span>
                        <span class="time">${{b.scheduled_date}} at ${{b.scheduled_time}}</span>
                    </div>
                `).join("");
            }}
        }} catch(e) {{
            console.error("Failed to load bookings:", e);
        }}
    }}
    
    loadBookings();
    setInterval(loadBookings, 15000);
</script>
    </body>
    </html>
    """)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "agent": "Aria",
        "calendar_connected": calendar_service.is_authenticated,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


# ──────────────────────────────────────────────
# Bookings API
# ──────────────────────────────────────────────

@app.get("/api/bookings")
async def api_bookings(limit: int = Query(default=20, le=100)):
    """Get recent bookings for the dashboard feed."""
    bookings = get_recent_bookings(limit)
    return {"bookings": bookings, "count": len(bookings)}


# ──────────────────────────────────────────────
# Google OAuth Flow
# ──────────────────────────────────────────────

@app.get("/auth/login")
async def auth_login():
    auth_url = calendar_service.get_auth_url()
    return RedirectResponse(url=auth_url)


@app.get("/auth/callback")
async def auth_callback(code: str = Query(...)):
    success = calendar_service.handle_callback(code)
    if success:
        return HTMLResponse(content="""
        <html><body style="font-family: 'Inter', sans-serif; text-align: center; padding: 80px; background: #050505; color: #e8e8e8;">
            <h1 style="color: #22c55e;">✅ Google Calendar Connected!</h1>
            <p style="color: #9ca3af; margin-top: 16px;">Aria can now schedule events on your calendar.</p>
            <p style="margin-top: 24px;"><a href="/" style="color: #8b5cf6; text-decoration: none;">← Back to Aria</a></p>
        </body></html>
        """)
    return HTMLResponse(content="<h1>❌ Authentication failed.</h1>", status_code=400)


# ──────────────────────────────────────────────
# Date/Time Parsing
# ──────────────────────────────────────────────

class ScheduleEventRequest(BaseModel):
    name: str
    date: str
    time: str
    title: Optional[str] = None
    duration_minutes: Optional[int] = 30


def parse_datetime(date_str: str, time_str: str, timezone: str = "America/New_York") -> datetime.datetime:
    """
    Parse natural language date/time into a timezone-aware datetime.
    Handles: 'tomorrow', 'next Monday', 'February 20th', '3pm', 'noon', etc.
    """
    target_tz = dateutil_tz.gettz(timezone)
    today = datetime.datetime.now(tz=target_tz)
    date_lower = date_str.strip().lower()

    # Handle common relative dates
    if date_lower in ("today",):
        base_date = today
    elif date_lower in ("tomorrow",):
        base_date = today + datetime.timedelta(days=1)
    else:
        try:
            base_date = date_parser.parse(date_str, fuzzy=True)
            # Ensure we don't schedule in the past
            if base_date.date() < today.date():
                candidate = base_date.replace(year=today.year)
                if candidate.date() < today.date():
                    candidate = base_date.replace(year=today.year + 1)
                base_date = candidate
        except Exception:
            base_date = today

    # Parse time
    try:
        time_part = date_parser.parse(time_str, fuzzy=True)
        result = base_date.replace(
            hour=time_part.hour, minute=time_part.minute, second=0, microsecond=0
        )
    except Exception:
        try:
            combined = f"{date_str} {time_str}"
            result = date_parser.parse(combined, fuzzy=True)
        except Exception as e:
            raise ValueError(f"Could not parse: '{date_str} {time_str}'. Error: {e}")

    # Ensure timezone-aware
    if result.tzinfo is None:
        result = result.replace(tzinfo=target_tz)

    return result


# ──────────────────────────────────────────────
# VAPI Tool Endpoints
# ──────────────────────────────────────────────

@app.post("/api/tool/schedule-event")
async def tool_schedule_event(request: Request):
    """Create a calendar event — called by Aria after user confirmation."""
    body = await request.json()
    tool_call = _extract_tool_call(body)
    if not tool_call:
        return JSONResponse(content={"error": "Invalid tool call"}, status_code=400)

    args = tool_call.get("function", {}).get("arguments", {})
    tool_call_id = tool_call.get("id", "")

    name = args.get("name", "Guest")
    date_str = args.get("date", "")
    time_str = args.get("time", "")
    title = args.get("title", None)
    duration = int(args.get("duration_minutes", 30))
    timezone = args.get("timezone", "America/New_York")

    # Auth check
    if not calendar_service.is_authenticated:
        return _vapi_tool_response(tool_call_id,
            "I'm sorry, the calendar isn't connected yet. Please ask the administrator to set it up.")

    # Parse datetime
    try:
        start_time = parse_datetime(date_str, time_str, timezone)
        end_time = start_time + datetime.timedelta(minutes=duration)
    except ValueError:
        return _vapi_tool_response(tool_call_id,
            "I couldn't quite understand that date or time. Could you say it once more?")

    # Check conflicts
    try:
        conflicts = calendar_service.check_conflicts(start_time, end_time, timezone)
        if conflicts:
            conflict_name = conflicts[0].get("summary", "another event")
            return _vapi_tool_response(tool_call_id,
                f"There's a conflict — you already have '{conflict_name}' at that time. Would you like to pick a different time?")
    except Exception as e:
        print(f"[Aria] Conflict check failed: {e}")
        # Don't block scheduling if conflict check fails — proceed with caution

    # Create event with retry
    event_title = title or f"Meeting with {name}"
    for attempt in range(2):
        try:
            event = calendar_service.create_event(
                summary=event_title,
                start_time=start_time,
                end_time=end_time,
                attendee_name=name,
                description=f"Scheduled by {name} via Aria Voice Agent",
                timezone=timezone,
            )

            # Log to SQLite
            try:
                log_booking(
                    caller_name=name,
                    meeting_title=event_title,
                    scheduled_date=start_time.strftime("%Y-%m-%d"),
                    scheduled_time=start_time.strftime("%I:%M %p"),
                    duration_minutes=duration,
                    timezone=timezone,
                    google_event_id=event["id"],
                    google_event_link=event["htmlLink"],
                )
            except Exception as log_err:
                print(f"[Aria] Booking log failed: {log_err}")

            formatted_date = start_time.strftime("%A, %B %d at %I:%M %p")
            return _vapi_tool_response(tool_call_id,
                f"Done! '{event_title}' is confirmed for {formatted_date}. It's on your Google Calendar. Is there anything else I can help with?")

        except Exception as e:
            print(f"[Aria] Event creation attempt {attempt + 1} failed: {e}")
            if attempt == 0:
                continue  # Retry once silently
            return _vapi_tool_response(tool_call_id,
                "I'm having a small technical hiccup with the calendar. Could we try a different time, or would you like me to try again?")


@app.post("/api/tool/check-availability")
async def tool_check_availability(request: Request):
    """Check if a time slot is available."""
    body = await request.json()
    tool_call = _extract_tool_call(body)
    if not tool_call:
        return JSONResponse(content={"error": "Invalid tool call"}, status_code=400)

    args = tool_call.get("function", {}).get("arguments", {})
    tool_call_id = tool_call.get("id", "")
    date_str = args.get("date", "")
    time_str = args.get("time", "")
    duration = int(args.get("duration_minutes", 30))

    if not calendar_service.is_authenticated:
        return _vapi_tool_response(tool_call_id, "Calendar not connected.")

    try:
        start_time = parse_datetime(date_str, time_str)
        end_time = start_time + datetime.timedelta(minutes=duration)
        conflicts = calendar_service.check_conflicts(start_time, end_time)

        if conflicts:
            conflict_name = conflicts[0].get("summary", "another event")
            return _vapi_tool_response(tool_call_id,
                f"That slot isn't available — there's '{conflict_name}' at that time. Would you like to try a different time, or should I check what's open?")

        formatted = start_time.strftime("%A, %B %d at %I:%M %p")
        return _vapi_tool_response(tool_call_id,
            f"{formatted} is available! Shall I go ahead and book it?")

    except ValueError:
        return _vapi_tool_response(tool_call_id,
            "I couldn't understand that date or time. Could you try again?")
    except Exception as e:
        print(f"[Aria] Availability check error: {e}")
        return _vapi_tool_response(tool_call_id,
            "I'm having trouble checking the calendar right now. Could you give me the time and I'll try to book it directly?")


@app.post("/api/tool/available-slots")
async def tool_available_slots(request: Request):
    """Find available time slots for a given date."""
    body = await request.json()
    tool_call = _extract_tool_call(body)
    if not tool_call:
        return JSONResponse(content={"error": "Invalid tool call"}, status_code=400)

    args = tool_call.get("function", {}).get("arguments", {})
    tool_call_id = tool_call.get("id", "")
    date_str = args.get("date", "tomorrow")
    preferred_period = args.get("preferred_period", "any")

    if not calendar_service.is_authenticated:
        return _vapi_tool_response(tool_call_id, "Calendar not connected.")

    try:
        # Define search window based on preferred period
        base_date = parse_datetime(date_str, "9:00 AM")
        
        if preferred_period == "morning":
            search_start = base_date.replace(hour=9, minute=0)
            search_end = base_date.replace(hour=12, minute=0)
        elif preferred_period == "afternoon":
            search_start = base_date.replace(hour=12, minute=0)
            search_end = base_date.replace(hour=17, minute=0)
        elif preferred_period == "evening":
            search_start = base_date.replace(hour=17, minute=0)
            search_end = base_date.replace(hour=20, minute=0)
        else:
            search_start = base_date.replace(hour=9, minute=0)
            search_end = base_date.replace(hour=18, minute=0)

        # Get all events in the window
        events = calendar_service.check_conflicts(search_start, search_end)

        # Find gaps (available 30-min slots)
        busy_times = []
        for evt in events:
            start = evt.get("start", {})
            end = evt.get("end", {})
            if "dateTime" in start:
                busy_start = date_parser.parse(start["dateTime"])
                busy_end = date_parser.parse(end["dateTime"])
                busy_times.append((busy_start, busy_end))
            elif "date" in start:
                # All-day event — entire day is busy
                return _vapi_tool_response(tool_call_id,
                    f"It looks like you have an all-day event on {date_str}. Would you like to try a different day?")

        # Generate available slots
        available = []
        current = search_start
        while current + datetime.timedelta(minutes=30) <= search_end and len(available) < 3:
            slot_end = current + datetime.timedelta(minutes=30)
            is_free = True
            for busy_start, busy_end in busy_times:
                if current < busy_end and slot_end > busy_start:
                    is_free = False
                    current = busy_end  # Skip past this event
                    break
            if is_free:
                available.append(current.strftime("%I:%M %p"))
                current += datetime.timedelta(minutes=60)  # Space out suggestions
            elif current == slot_end:
                current += datetime.timedelta(minutes=30)

        if available:
            slots_str = ", ".join(available[:-1]) + f", or {available[-1]}" if len(available) > 1 else available[0]
            formatted_date = base_date.strftime("%A, %B %d")
            return _vapi_tool_response(tool_call_id,
                f"On {formatted_date}, I have these slots open: {slots_str}. Which works best for you?")
        else:
            return _vapi_tool_response(tool_call_id,
                f"It looks like {date_str} is pretty packed. Would you like to try a different day?")

    except Exception as e:
        print(f"[Aria] Available slots error: {e}\n{traceback.format_exc()}")
        return _vapi_tool_response(tool_call_id,
            "I'm having trouble checking the schedule. Could you suggest a specific time and I'll see if it works?")


# ──────────────────────────────────────────────
# VAPI Webhook
# ──────────────────────────────────────────────

@app.post("/api/webhook/vapi")
async def vapi_webhook(request: Request):
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


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _extract_tool_call(body: dict) -> Optional[dict]:
    """Extract tool call from VAPI's request payload."""
    message = body.get("message", {})
    tool_calls = message.get("toolCalls", [])
    if tool_calls:
        return tool_calls[0]
    if "toolCall" in message:
        return message["toolCall"]
    if "function" in body:
        return body
    return None


def _vapi_tool_response(tool_call_id: str, result: str) -> JSONResponse:
    """Format response for VAPI's tool result contract."""
    return JSONResponse(content={
        "results": [{"toolCallId": tool_call_id, "result": result}]
    })


# ──────────────────────────────────────────────
# Direct API (Testing)
# ──────────────────────────────────────────────

@app.post("/api/direct/schedule")
async def direct_schedule(req: ScheduleEventRequest):
    """Direct endpoint for curl/Postman testing."""
    if not calendar_service.is_authenticated:
        return JSONResponse(content={"error": "Not authenticated. Visit /auth/login"}, status_code=401)

    try:
        start_time = parse_datetime(req.date, req.time)
        end_time = start_time + datetime.timedelta(minutes=req.duration_minutes)
    except ValueError as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)

    conflicts = calendar_service.check_conflicts(start_time, end_time)
    if conflicts:
        return JSONResponse(content={
            "status": "conflict",
            "conflicts": [{"summary": e.get("summary"), "start": e.get("start")} for e in conflicts],
        })

    event = calendar_service.create_event(
        summary=req.title or f"Meeting with {req.name}",
        start_time=start_time,
        end_time=end_time,
        attendee_name=req.name,
    )

    # Log it
    log_booking(
        caller_name=req.name,
        meeting_title=req.title or f"Meeting with {req.name}",
        scheduled_date=start_time.strftime("%Y-%m-%d"),
        scheduled_time=start_time.strftime("%I:%M %p"),
        duration_minutes=req.duration_minutes,
        timezone="America/New_York",
        google_event_id=event["id"],
        google_event_link=event["htmlLink"],
    )

    return {"status": "created", "event": event}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app.server:app", host="0.0.0.0", port=port, reload=True)
