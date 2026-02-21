"""
Database — Bookings & Users
=============================
SQLite-backed storage for:
  - users: Google Calendar credentials per user (multi-tenant)
  - bookings: log of all scheduled events
"""

import sqlite3
import json
import datetime
from typing import Optional

from app.config import settings


import os

def _get_conn():
    os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize all tables."""
    conn = _get_conn()
    
    # Users table — stores Google Calendar credentials per user
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            name TEXT,
            google_token_json TEXT NOT NULL,
            connected_at TEXT NOT NULL,
            last_used_at TEXT
        )
    """)
    
    # Bookings table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT,
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


# ──────────────────────────────────────────────
# User Credential Management
# ──────────────────────────────────────────────

def save_user_credentials(email: str, token_json: str, name: str = None):
    """Save or update a user's Google Calendar credentials."""
    conn = _get_conn()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    
    if existing:
        conn.execute(
            "UPDATE users SET google_token_json = ?, name = COALESCE(?, name), connected_at = ? WHERE email = ?",
            (token_json, name, now, email)
        )
    else:
        conn.execute(
            "INSERT INTO users (email, name, google_token_json, connected_at) VALUES (?, ?, ?, ?)",
            (email, name, token_json, now)
        )
    
    conn.commit()
    conn.close()


def get_user_credentials(email: str) -> Optional[str]:
    """Get a user's stored Google token JSON. Returns None if not found."""
    conn = _get_conn()
    row = conn.execute("SELECT google_token_json FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    
    if row:
        return row["google_token_json"]
    return None


def update_user_token(email: str, token_json: str):
    """Update a user's token after refresh."""
    conn = _get_conn()
    conn.execute(
        "UPDATE users SET google_token_json = ?, last_used_at = ? WHERE email = ?",
        (token_json, datetime.datetime.now(datetime.timezone.utc).isoformat(), email)
    )
    conn.commit()
    conn.close()


def get_all_users() -> list[dict]:
    """Get all connected users (for the dashboard)."""
    conn = _get_conn()
    rows = conn.execute("SELECT email, name, connected_at, last_used_at FROM users ORDER BY connected_at DESC").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def delete_user(email: str):
    """Remove a user's credentials."""
    conn = _get_conn()
    conn.execute("DELETE FROM users WHERE email = ?", (email,))
    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
# Booking Log
# ──────────────────────────────────────────────

def log_booking(
    caller_name: str,
    meeting_title: str,
    scheduled_date: str,
    scheduled_time: str,
    duration_minutes: int,
    timezone: str,
    google_event_id: str,
    google_event_link: str,
    user_email: str = None,
):
    """Log a successful booking."""
    conn = _get_conn()
    conn.execute(
        """INSERT INTO bookings 
           (user_email, caller_name, meeting_title, scheduled_date, scheduled_time, 
            duration_minutes, timezone, google_event_id, google_event_link, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            user_email,
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
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM bookings ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
