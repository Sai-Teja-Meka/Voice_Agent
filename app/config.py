"""
Centralized Configuration
=========================
All environment variables and app settings in one place.
No hardcoded values scattered across files.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""

    # Server
    SERVER_URL: str = os.getenv("SERVER_URL", "http://localhost:8000")
    PORT: int = int(os.getenv("PORT", 8000))

    # Google Calendar OAuth
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI", f"{SERVER_URL}/auth/callback")
    GOOGLE_TOKEN_JSON: str = os.getenv("GOOGLE_TOKEN_JSON", "")

    # VAPI
    VAPI_API_KEY: str = os.getenv("VAPI_API_KEY", "")
    VAPI_PUBLIC_KEY: str = os.getenv("VAPI_PUBLIC_KEY", "")
    VAPI_ASSISTANT_ID: str = os.getenv("VAPI_ASSISTANT_ID", "")

    # Database
    DB_PATH: str = os.getenv("DB_PATH", "bookings.db")

    # Defaults
    DEFAULT_TIMEZONE: str = os.getenv("DEFAULT_TIMEZONE", "America/New_York")
    DEFAULT_DURATION_MINUTES: int = int(os.getenv("DEFAULT_DURATION_MINUTES", 30))
    MAX_CALL_DURATION_SECONDS: int = int(os.getenv("MAX_CALL_DURATION_SECONDS", 600))


settings = Settings()
