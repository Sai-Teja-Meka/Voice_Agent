"""
Google Calendar Service
=======================
Handles OAuth2 authentication and calendar event CRUD operations.
Supports conflict detection — because a great scheduling agent 
doesn't double-book you.
"""

import os
import json
import datetime
from pathlib import Path
from typing import Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from dotenv import load_dotenv

load_dotenv()

# OAuth2 scopes
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Token storage path
TOKEN_PATH = Path("token.json")

# OAuth client config built from env vars
CLIENT_CONFIG = {
    "web": {
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "redirect_uris": [os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback")],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}


class GoogleCalendarService:
    """Manages Google Calendar operations with OAuth2 authentication."""

    def __init__(self):
        self.creds: Optional[Credentials] = None
        self.service = None
        self._load_credentials()

    def _load_credentials(self):
        """Load stored credentials if they exist and are valid."""
        token_json = os.getenv("GOOGLE_TOKEN_JSON")
        if token_json:
            self.creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
        if TOKEN_PATH.exists():
            self.creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

        if self.creds and self.creds.expired and self.creds.refresh_token:
            self.creds.refresh(Request())
            self._save_credentials()

        if self.creds and self.creds.valid:
            self.service = build("calendar", "v3", credentials=self.creds)

    def _save_credentials(self):
        """Persist credentials to disk."""
        with open(TOKEN_PATH, "w") as f:
            f.write(self.creds.to_json())

    @property
    def is_authenticated(self) -> bool:
        if self.creds and self.creds.expired and self.creds.refresh_token:
            try:
                self.creds.refresh(Request())
                self._save_credentials()
                self.service = build("calendar", "v3", credentials=self.creds)
            except Exception as e:
                print(f"[CalendarService] Token refresh failed: {e}")
                return False
        return self.creds is not None and self.creds.valid

    def get_auth_url(self) -> str:
        """Generate the Google OAuth2 authorization URL."""
        flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES)
        flow.redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback")
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        return auth_url

    def handle_callback(self, authorization_code: str) -> bool:
        """Exchange authorization code for credentials."""
        try:
            flow = Flow.from_client_config(CLIENT_CONFIG, scopes=SCOPES)
            flow.redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback")
            flow.fetch_token(code=authorization_code)
            self.creds = flow.credentials
            self._save_credentials()
            self.service = build("calendar", "v3", credentials=self.creds)
            return True
        except Exception as e:
            print(f"[CalendarService] OAuth callback error: {e}")
            return False

    def _to_rfc3339(self, dt: datetime.datetime, timezone: str = "America/New_York") -> str:
        """
        Convert a datetime to RFC3339 format with timezone.
        Google Calendar API requires timezone-aware datetimes — naive = 400 error.
        """
        from dateutil import tz as dateutil_tz
        
        if dt.tzinfo is None:
            # Attach the target timezone to naive datetimes
            target_tz = dateutil_tz.gettz(timezone)
            dt = dt.replace(tzinfo=target_tz)
        return dt.isoformat()

    def check_conflicts(
        self, start_time: datetime.datetime, end_time: datetime.datetime,
        timezone: str = "America/New_York"
    ) -> list[dict]:
        """
        Check for conflicting events in the given time window.
        Returns list of conflicting events (empty = no conflicts).
        """
        if not self.is_authenticated:
            raise Exception("Not authenticated with Google Calendar")

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

    def create_event(
        self,
        summary: str,
        start_time: datetime.datetime,
        end_time: datetime.datetime,
        attendee_name: Optional[str] = None,
        description: Optional[str] = None,
        timezone: str = "America/New_York",
    ) -> dict:
        """
        Create a calendar event. Returns the created event data.
        
        This is the core action — the voice agent calls this after 
        collecting and confirming all details.
        """
        if not self.is_authenticated:
            raise Exception("Not authenticated with Google Calendar")

        event_body = {
            "summary": summary or f"Meeting with {attendee_name or 'Guest'}",
            "description": description or f"Scheduled via Vikara Voice Agent for {attendee_name or 'Guest'}",
            "start": {
                "dateTime": start_time.isoformat(),
                "timeZone": timezone,
            },
            "end": {
                "dateTime": end_time.isoformat(),
                "timeZone": timezone,
            },
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 10},
                ],
            },
        }

        created_event = (
            self.service.events()
            .insert(calendarId="primary", body=event_body)
            .execute()
        )

        return {
            "id": created_event["id"],
            "summary": created_event["summary"],
            "start": created_event["start"],
            "end": created_event["end"],
            "htmlLink": created_event.get("htmlLink", ""),
            "status": "confirmed",
        }

    def list_upcoming_events(self, max_results: int = 5) -> list[dict]:
        """List upcoming events — useful for conflict context."""
        if not self.is_authenticated:
            raise Exception("Not authenticated with Google Calendar")

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        events_result = (
            self.service.events()
            .list(
                calendarId="primary",
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        return events_result.get("items", [])


# Singleton instance
calendar_service = GoogleCalendarService()
