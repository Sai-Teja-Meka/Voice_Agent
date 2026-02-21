"""
Auth Routes — /auth/*
=====================
Multi-tenant Google OAuth2 flow.
Each user connects their own Google Calendar.
"""

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from app.calendar_service import calendar_service
from app.database import get_all_users

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/connect")
async def connect_calendar():
    """Start OAuth flow for a new user to connect their calendar."""
    auth_url = calendar_service.get_auth_url()
    return RedirectResponse(url=auth_url)


@router.get("/login")
async def login():
    """Legacy endpoint — redirects to /auth/connect."""
    return RedirectResponse(url="/auth/connect")


@router.get("/callback")
async def callback(code: str = Query(...), state: str = Query(default="")):
    """Handle Google OAuth callback — saves user credentials to DB."""
    email = calendar_service.handle_callback(code)
    
    if email:
        return HTMLResponse(content=f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: 'Inter', -apple-system, sans-serif;
                    text-align: center;
                    padding: 80px 24px;
                    background: #050505;
                    color: #e8e8e8;
                }}
                .success {{ color: #22c55e; font-size: 2rem; margin-bottom: 16px; }}
                .email {{ color: #8b5cf6; font-weight: 600; }}
                .info {{ color: #9ca3af; margin-top: 12px; line-height: 1.6; }}
                a {{ color: #8b5cf6; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
                .back {{ margin-top: 32px; }}
            </style>
        </head>
        <body>
            <div class="success">✅ Calendar Connected!</div>
            <p class="info">
                Signed in as <span class="email">{email}</span><br>
                Aria can now schedule events on your Google Calendar.
            </p>
            <p class="info">
                When you talk to Aria, just tell her your email address<br>
                and she'll book directly on your calendar.
            </p>
            <p class="back"><a href="/">← Back to Aria</a></p>
        </body>
        </html>
        """)
    
    return HTMLResponse(content="""
    <html><body style="font-family: sans-serif; text-align: center; padding: 80px; background: #050505; color: #e8e8e8;">
        <h1 style="color: #ef4444;">❌ Authentication Failed</h1>
        <p style="color: #9ca3af;">Could not connect your calendar. Please try again.</p>
        <p><a href="/auth/connect" style="color: #8b5cf6;">Try Again</a></p>
    </body></html>
    """, status_code=400)


@router.get("/users")
async def list_connected_users():
    """List all users who have connected their calendars."""
    users = get_all_users()
    return {"users": users, "count": len(users)}
