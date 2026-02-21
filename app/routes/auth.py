"""
Auth Routes — /auth/*
=====================
Google OAuth2 flow for calendar authorization.
"""

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from app.calendar_service import calendar_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login():
    """Redirect to Google OAuth consent screen."""
    auth_url = calendar_service.get_auth_url()
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def callback(code: str = Query(...)):
    """Handle Google OAuth callback."""
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
