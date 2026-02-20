"""
Page & API Routes
==================
Landing page, health check, and bookings feed.
"""

import datetime
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from app.config import settings
from app.calendar_service import calendar_service
from app.database import get_recent_bookings

router = APIRouter(tags=["pages"])

# Load the frontend HTML template once
FRONTEND_PATH = Path(__file__).parent.parent.parent / "frontend" / "index.html"


@router.get("/")
async def landing_page():
    """Serve the immersive 3D frontend with injected config."""
    try:
        html = FRONTEND_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Frontend not found. Check deployment.</h1>", status_code=500)

    # Inject runtime config
    html = html.replace("%%VAPI_PUBLIC_KEY%%", settings.VAPI_PUBLIC_KEY)
    html = html.replace("%%VAPI_ASSISTANT_ID%%", settings.VAPI_ASSISTANT_ID)

    return HTMLResponse(content=html)


@router.get("/health")
async def health():
    return {
        "status": "healthy",
        "agent": "Aria",
        "calendar_connected": calendar_service.is_authenticated,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


@router.get("/api/bookings")
async def api_bookings(limit: int = Query(default=20, le=100)):
    """Recent bookings feed for the dashboard."""
    bookings = get_recent_bookings(limit)
    return {"bookings": bookings, "count": len(bookings)}
