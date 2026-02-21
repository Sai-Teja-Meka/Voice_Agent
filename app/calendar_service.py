"""
Google Calendar Service — Multi-Tenant
========================================
Supports multiple users, each with their own Google Calendar credentials.

Flow:
  1. User visits /auth/connect → Google OAuth → credentials saved to DB
  2. When Aria schedules for a user, we load THEIR credentials from DB
  3. Each user gets their own Google Calendar API client
  
Backward compatible: still supports single-tenant via GOOGLE_TOKEN_JSON env var.
"""

import os
import json
import datetime
from typing import Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from app.config import settings
from app.database import get_user_credentials, save_user_credentials, update_user_token

# OAuth2 scopes
SCOPES = ["https://www.googleapis.com/auth/calendar", "https://www.googleapis.com/auth/userinfo.email"]

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
    - get_auth_url(email) → starts OAuth for a specific user  
    - handle_callback(code, state) → saves credentials for the user
    
    Also supports legacy single-tenant mode via is_authenticated / default client.
    """

    def __init__(self):
        self._default_creds: Optional[Credentials] = None
        self._default_service = None
        self._load_default_credentials()

    def _load_default_credentials(self):
        """Load default credentials from env var (backward compatible)."""
        token_json = os.getenv("GOOGLE_TOKEN_JSON")
        if token_json:
            try:
                self._default_creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
                if self._default_creds.expired and self._default_creds.refresh_token:
                    self._default_creds.refresh(Request())
                if self._default_creds.valid:
                    self._default_service = build("calendar", "v3", credentials=self._default_creds)
            except Exception as e:
                print(f"[CalendarService] Default credential load failed: {e}")

    @property
    def is_authenticated(self) -> bool:
        """Check if default (legacy) credentials are valid."""
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
        Loads their credentials from the database, refreshes if needed.
        Returns None if user hasn't connected their calendar.
        """
        token_json = get_user_credentials(email)
        if not token_json:
            return None

        try:
            creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)

            # Refresh if expired
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
            return CalendarClient(self._default_creds, email="default")
        return None

    def resolve_client(self, email: str = None) -> Optional[CalendarClient]:
        """
        Smart resolution: try user-specific client first, fall back to default.
        This is what tool endpoints should call.
        """
        if email:
            client = self.get_client_for_user(email)
            if client:
                return client

        # Fall back to default
        return self.get_default_client()

    # ──────────────────────────────────────────
    # OAuth Flow
    # ──────────────────────────────────────────

    def get_auth_url(self, state: str = None) -> str:
        """Generate Google OAuth URL. State can carry user email for callback."""
        flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES)
        flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
            state=state or "",
        )
        return auth_url

    def handle_callback(self, authorization_code: str) -> Optional[str]:
        """
        Exchange auth code for credentials.
        Returns the user's email on success, None on failure.
        Saves credentials to the database.
        """
        try:
            flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES)
            flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
            flow.fetch_token(code=authorization_code)
            creds = flow.credentials

            # Get the user's email from Google
            from googleapiclient.discovery import build as google_build
            oauth2_service = google_build("oauth2", "v2", credentials=creds)
            user_info = oauth2_service.userinfo().get().execute()
            email = user_info.get("email", "")
            name = user_info.get("name", "")

            if not email:
                print("[CalendarService] Could not get email from Google")
                return None

            # Save to database
            save_user_credentials(email, creds.to_json(), name)

            # Also update default creds for backward compat
            self._default_creds = creds
            self._default_service = build("calendar", "v3", credentials=creds)

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
