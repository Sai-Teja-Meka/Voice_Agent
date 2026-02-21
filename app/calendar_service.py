"""
Google Calendar Service — Multi-Tenant
========================================
Supports multiple users, each with their own Google Calendar credentials.

Flow:
  1. User visits /auth/connect → Google OAuth → credentials saved to DB
  2. When Aria schedules for a user, we load THEIR credentials from DB
  3. Each user gets their own Google Calendar API client

Backward compatible: still supports single-tenant via GOOGLE_TOKEN_JSON env var.

Bug fixes applied:
  - [#1] handle_callback no longer overwrites _default_creds (user cross-contamination)
  - [#2] resolve_client no longer silently falls back when email is given (lying confirmation)
  - [#3] CSRF state tokens with TTL expiry (lives here, consumed in auth.py)
  - [#5] threading.Lock guards all mutations of _default_creds
  - [#6] Email format validated before DB lookup
"""

import os
import re
import json
import time
import secrets
import datetime
import threading
from typing import Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from app.config import settings
from app.database import get_user_credentials, save_user_credentials, update_user_token

# OAuth2 scopes
SCOPES = ["https://www.googleapis.com/auth/calendar"]
CONNECT_SCOPES = ["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/userinfo.email"]

# OAuth client config
CLIENT_CONFIG = {
    "web": {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

# Fix #6 — email format validation regex
_EMAIL_RE = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')

# Fix #3 — CSRF state store: {token: expiry_timestamp}
# Tokens expire after 10 minutes to prevent memory leaks
_STATE_TTL_SECONDS = 600
_pending_states: dict[str, float] = {}
_states_lock = threading.Lock()


def _issue_state_token() -> str:
    """Generate a CSRF state token and register it with a TTL."""
    token = secrets.token_urlsafe(32)
    now = time.monotonic()
    with _states_lock:
        # Prune expired tokens on each issue to prevent unbounded growth
        expired = [k for k, exp in _pending_states.items() if now > exp]
        for k in expired:
            del _pending_states[k]
        _pending_states[token] = now + _STATE_TTL_SECONDS
    return token


def validate_and_consume_state(token: str) -> bool:
    """Validate a CSRF state token and remove it (one-time use). Returns True if valid."""
    if not token:
        return False
    now = time.monotonic()
    with _states_lock:
        expiry = _pending_states.get(token)
        if expiry is None:
            return False  # Unknown token
        del _pending_states[token]  # Consume — one-time use
        if now > expiry:
            return False  # Expired
    return True


class CalendarClient:
    """A Google Calendar client for a specific user."""

    def __init__(self, creds: Credentials, email: str = None):
        self.creds = creds
        self.email = email
        self.service = build("calendar", "v3", credentials=creds)

    def _to_rfc3339(self, dt: datetime.datetime, timezone: str = "America/New_York") -> str:
        from dateutil import tz as dateutil_tz
        if dt.tzinfo is None:
            target_tz = dateutil_tz.gettz(timezone)
            dt = dt.replace(tzinfo=target_tz)
        return dt.isoformat()

    def check_conflicts(self, start_time: datetime.datetime, end_time: datetime.datetime,
                        timezone: str = "America/New_York") -> list[dict]:
        events_result = (
            self.service.events()
            .list(
                calendarId="primary",
                timeMin=self._to_rfc3339(start_time, timezone),
                timeMax=self._to_rfc3339(end_time, timezone),
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        return events_result.get("items", [])

    def create_event(self, summary: str, start_time: datetime.datetime, end_time: datetime.datetime,
                     attendee_name: str = None, description: str = None,
                     timezone: str = "America/New_York") -> dict:
        event_body = {
            "summary": summary or f"Meeting with {attendee_name or 'Guest'}",
            "description": description or f"Scheduled via Aria for {attendee_name or 'Guest'}",
            "start": {"dateTime": start_time.isoformat(), "timeZone": timezone},
            "end": {"dateTime": end_time.isoformat(), "timeZone": timezone},
            "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 10}]},
        }
        created = self.service.events().insert(calendarId="primary", body=event_body).execute()
        return {
            "id": created["id"],
            "summary": created["summary"],
            "start": created["start"],
            "end": created["end"],
            "htmlLink": created.get("htmlLink", ""),
            "status": "confirmed",
        }

    def list_upcoming_events(self, max_results: int = 5) -> list[dict]:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        events_result = (
            self.service.events()
            .list(calendarId="primary", timeMin=now, maxResults=max_results,
                  singleEvents=True, orderBy="startTime")
            .execute()
        )
        return events_result.get("items", [])


class GoogleCalendarService:
    """
    Multi-tenant calendar service.

    - get_client_for_user(email) → returns a CalendarClient for that user
    - get_auth_url() → starts OAuth, returns (url, state_token)
    - handle_callback(code) → saves credentials for the user

    Also supports legacy single-tenant mode via is_authenticated / default client.
    """

    def __init__(self):
        # Fix #5 — lock guards all reads/writes of _default_creds
        self._lock = threading.Lock()
        self._default_creds: Optional[Credentials] = None
        self._default_service = None
        self._load_default_credentials()

    def _load_default_credentials(self):
        """Load default credentials from env var (backward compatible).
        This is the ONLY place _default_creds should ever be set.
        """
        token_json = os.getenv("GOOGLE_TOKEN_JSON")
        if token_json:
            try:
                creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
                if creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                if creds.valid:
                    with self._lock:
                        self._default_creds = creds
                        self._default_service = build("calendar", "v3", credentials=creds)
            except Exception as e:
                print(f"[CalendarService] Default credential load failed: {e}")

    @property
    def is_authenticated(self) -> bool:
        """Check if default (legacy) credentials are valid."""
        # Fix #5 — lock around credential refresh mutation
        with self._lock:
            if self._default_creds and self._default_creds.expired and self._default_creds.refresh_token:
                try:
                    self._default_creds.refresh(Request())
                    self._default_service = build("calendar", "v3", credentials=self._default_creds)
                except Exception:
                    return False
            return self._default_creds is not None and self._default_creds.valid

    # ──────────────────────────────────────────
    # Multi-Tenant: Per-User Clients
    # ──────────────────────────────────────────

    def get_client_for_user(self, email: str) -> Optional[CalendarClient]:
        """
        Get a CalendarClient for a specific user.
        Returns None if user hasn't connected their calendar or email is invalid.
        """
        # Fix #6 — validate email format before touching the DB
        if not _EMAIL_RE.match(email):
            print(f"[CalendarService] Rejected invalid email format: {email!r}")
            return None

        token_json = get_user_credentials(email)
        if not token_json:
            return None

        try:
            creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                update_user_token(email, creds.to_json())
            if creds.valid:
                return CalendarClient(creds, email)
        except Exception as e:
            print(f"[CalendarService] Failed to load credentials for {email}: {e}")

        return None

    def get_default_client(self) -> Optional[CalendarClient]:
        """Get the default (legacy single-tenant) client."""
        if self.is_authenticated:
            with self._lock:
                return CalendarClient(self._default_creds, email="default")
        return None

    def resolve_client(self, email: str = None) -> Optional[CalendarClient]:
        """
        Resolve the correct calendar client for a tool call.

        Fix #2 — when email is explicitly provided, ONLY return that user's
        client or None. Never fall back silently to the default: doing so
        would book on the wrong calendar and then confirm with a lie
        ("booked on bob@example.com's calendar").

        Only fall back to the default when no email is given at all
        (single-tenant / personal assistant mode).
        """
        if email:
            # Strict: user's client or None — no silent fallback
            return self.get_client_for_user(email)
        # No email given — use default (single-tenant mode)
        return self.get_default_client()

    # ──────────────────────────────────────────
    # OAuth Flow
    # ──────────────────────────────────────────

    def get_auth_url(self) -> tuple[str, str]:
        """
        Generate Google OAuth URL with a CSRF state token.

        Fix #3 — returns (auth_url, state_token). The caller (auth route)
        stores the state in a signed cookie and validates it in the callback.

        Returns:
            (auth_url, state_token)
        """
        state = _issue_state_token()
        flow = Flow.from_client_config(CLIENT_CONFIG, scopes=CONNECT_SCOPES)
        flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state,
        )
        return auth_url, state

    def handle_callback(self, authorization_code: str) -> Optional[str]:
        """
        Exchange auth code for credentials.
        Returns the user's email on success, None on failure.
        Saves credentials to the database only.

        Fix #1 — does NOT touch _default_creds. Per-user credentials are
        stored in the DB only, keyed by email. The default client is
        immutable after startup.
        """
        try:
            flow = Flow.from_client_config(CLIENT_CONFIG, scopes=CONNECT_SCOPES)
            flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
            flow.fetch_token(code=authorization_code)
            creds = flow.credentials

            from googleapiclient.discovery import build as google_build
            oauth2_service = google_build("oauth2", "v2", credentials=creds)
            user_info = oauth2_service.userinfo().get().execute()
            email = user_info.get("email", "")
            name = user_info.get("name", "")

            if not email:
                print("[CalendarService] Could not get email from Google")
                return None

            # Fix #1 — DB only, never _default_creds
            save_user_credentials(email, creds.to_json(), name)
            print(f"[CalendarService] ✅ Connected calendar for {email}")
            return email

        except Exception as e:
            print(f"[CalendarService] OAuth callback error: {e}")
            return None

    # ──────────────────────────────────────────
    # Legacy Single-Tenant Methods (backward compat)
    # ──────────────────────────────────────────

    def check_conflicts(self, start_time, end_time, timezone="America/New_York"):
        client = self.get_default_client()
        if not client:
            raise Exception("Not authenticated")
        return client.check_conflicts(start_time, end_time, timezone)

    def create_event(self, summary, start_time, end_time, attendee_name=None,
                     description=None, timezone="America/New_York"):
        client = self.get_default_client()
        if not client:
            raise Exception("Not authenticated")
        return client.create_event(summary, start_time, end_time, attendee_name, description, timezone)


# Singleton
calendar_service = GoogleCalendarService()