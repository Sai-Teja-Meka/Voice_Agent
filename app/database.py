"""
Database — Booking Log
=======================
SQLite-backed booking log for tracking all scheduled events.
Every successful booking gets recorded with full metadata.
"""

import sqlite3
import datetime
from typing import Optional

from app.config import settings


def init_db():
    """Initialize the bookings table."""
    conn = sqlite3.connect(settings.DB_PATH)
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
    """Log a successful booking."""
    conn = sqlite3.connect(settings.DB_PATH)
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
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM bookings ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
