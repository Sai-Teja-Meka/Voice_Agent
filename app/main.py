"""
Aria — Voice Scheduling Agent
===============================
Application factory. Creates the FastAPI app and wires all route modules.

Architecture:
  app/
  ├── main.py            ← You are here (app factory)
  ├── config.py          ← Centralized settings
  ├── models.py          ← Pydantic schemas
  ├── database.py        ← SQLite booking log
  ├── calendar_service.py← Google Calendar integration
  ├── datetime_utils.py  ← Date/time parsing
  ├── vapi_utils.py      ← VAPI helper functions
  └── routes/
      ├── tools.py       ← /tools/api/v1/* (VAPI tool endpoints)
      ├── auth.py        ← /auth/* (Google OAuth)
      ├── pages.py       ← Landing page, health, bookings API
      └── webhooks.py    ← /api/webhook/* (VAPI events)
"""

import os
from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.calendar_service import calendar_service
from app.routes import tools, auth, pages, webhooks


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown lifecycle."""
    init_db()
    print("=" * 55)
    print("  🎙️  Aria — Voice Scheduling Agent")
    print(f"  📅  Calendar: {'✅ Connected' if calendar_service.is_authenticated else '❌ Not connected'}")
    print(f"  🌐  Server: {settings.SERVER_URL}")
    print(f"  📊  Booking DB: {settings.DB_PATH}")
    print("=" * 55)
    yield
    print("Shutting down Aria...")


app = FastAPI(
    title="Aria — Voice Scheduling Agent",
    description="Real-time voice assistant for intelligent calendar scheduling",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register route modules
app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(tools.router)
app.include_router(webhooks.router)


# ──────────────────────────────────────────────
# Direct API (Testing — no VAPI needed)
# ──────────────────────────────────────────────

from app.models import DirectScheduleRequest
from app.datetime_utils import parse_datetime
from app.database import log_booking
from fastapi.responses import JSONResponse
import datetime


@app.post("/api/direct/schedule", tags=["testing"])
async def direct_schedule(req: DirectScheduleRequest):
    """Direct endpoint for curl/Postman testing without VAPI."""
    if not calendar_service.is_authenticated:
        return JSONResponse(content={"error": "Not authenticated. Visit /auth/login"}, status_code=401)

    try:
        start_time = parse_datetime(req.date, req.time)
        end_time = start_time + datetime.timedelta(minutes=req.duration_minutes)
    except ValueError as e:
        return JSONResponse(content={"error": str(e)}, status_code=400)

    conflicts = await asyncio.to_thread(calendar_service.check_conflicts, start_time, end_time)
    if conflicts:
        return JSONResponse(content={
            "status": "conflict",
            "conflicts": [{"summary": e.get("summary"), "start": e.get("start")} for e in conflicts],
        })

    event = await asyncio.to_thread(calendar_service.create_event,
        summary=req.title or f"Meeting with {req.name}",
        start_time=start_time,
        end_time=end_time,
        attendee_name=req.name,
    )

    await asyncio.to_thread(log_booking,
        caller_name=req.name,
        meeting_title=req.title or f"Meeting with {req.name}",
        scheduled_date=start_time.strftime("%Y-%m-%d"),
        scheduled_time=start_time.strftime("%I:%M %p"),
        duration_minutes=req.duration_minutes,
        timezone=settings.DEFAULT_TIMEZONE,
        google_event_id=event["id"],
        google_event_link=event["htmlLink"],
    )

    return {"status": "created", "event": event}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
