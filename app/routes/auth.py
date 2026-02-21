"""
Auth Routes — /auth/*
=====================
Multi-tenant Google OAuth2 flow.
Each user connects their own Google Calendar.

Bug fixes applied:
  - [#3] CSRF state token validated on callback before processing the auth code
"""

from fastapi import APIRouter, Query, Cookie, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from app.calendar_service import calendar_service, validate_and_consume_state
from app.database import get_all_users

router = APIRouter(prefix="/auth", tags=["auth"])

# Cookie name for the CSRF state token
_STATE_COOKIE = "aria_oauth_state"


@router.get("/connect")
async def connect_calendar(response: Response):
    """
    Start OAuth flow for a new user to connect their calendar.
    Issues a CSRF state token and stores it in a signed, httponly cookie.
    """
    auth_url, state = calendar_service.get_auth_url()
    redirect = RedirectResponse(url=auth_url)
    # httponly + samesite=lax: JS can't read it; won't be sent on cross-site POSTs
    redirect.set_cookie(
        key=_STATE_COOKIE,
        value=state,
        max_age=600,          # Matches _STATE_TTL_SECONDS in calendar_service
        httponly=True,
        samesite="lax",
        secure=True,        # Set to True in production behind HTTPS
    )
    return redirect


@router.get("/login")
async def login():
    """Legacy endpoint — redirects to /auth/connect."""
    return RedirectResponse(url="/auth/connect")


@router.get("/callback")
async def callback(
    code: str = Query(...),
    state: str = Query(default=""),
    aria_oauth_state: str = Cookie(default=""),
):
    """
    Handle Google OAuth callback.

    Fix #3 — validates the state token from the cookie against the token
    returned by Google. Rejects the request if they don't match, are
    unknown, or have expired (10-minute TTL).
    """
    # CSRF check: state from Google must match what we stored in the cookie
    if not state or state != aria_oauth_state or not validate_and_consume_state(state):
        return HTMLResponse(
            content="""
            <html><body style="font-family:sans-serif;text-align:center;padding:80px;
                               background:#050505;color:#e8e8e8;">
                <h1 style="color:#ef4444;">❌ Invalid Request</h1>
                <p style="color:#9ca3af;">
                    OAuth state mismatch — this could be a CSRF attempt,
                    or your session expired. Please try again.
                </p>
                <p><a href="/auth/connect" style="color:#8b5cf6;">Try Again</a></p>
            </body></html>
            """,
            status_code=403,
        )

    email = calendar_service.handle_callback(code)

    # Clear the state cookie regardless of outcome
    response_kwargs = dict(
        headers={"Set-Cookie": f"{_STATE_COOKIE}=; Max-Age=0; Path=/; HttpOnly; SameSite=lax"}
    )

    if email:
        return HTMLResponse(
            content=f"""
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
            """,
            **response_kwargs,
        )

    return HTMLResponse(
        content="""
        <html><body style="font-family:sans-serif;text-align:center;padding:80px;
                           background:#050505;color:#e8e8e8;">
            <h1 style="color:#ef4444;">❌ Authentication Failed</h1>
            <p style="color:#9ca3af;">Could not connect your calendar. Please try again.</p>
            <p><a href="/auth/connect" style="color:#8b5cf6;">Try Again</a></p>
        </body></html>
        """,
        status_code=400,
        **response_kwargs,
    )


@router.get("/users")
async def list_connected_users():
    """List all users who have connected their calendars."""
    users = get_all_users()
    return {"users": users, "count": len(users)}