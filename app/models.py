"""
Pydantic Models & Schemas
==========================
Typed, validated schemas for all API inputs and outputs.
Used by both tool endpoints and direct API.
"""

from typing import Optional
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# Tool Call Schemas (VAPI → Server)
# ──────────────────────────────────────────────

class ScheduleEventArgs(BaseModel):
    """Arguments for the schedule_event tool."""
    name: str = Field(..., description="Caller's name")
    date: str = Field(..., description="Meeting date (natural language or ISO)")
    time: str = Field(..., description="Meeting time (e.g., '3:00 PM', '15:00')")
    title: Optional[str] = Field(None, description="Meeting title")
    duration_minutes: int = Field(30, ge=5, le=480, description="Duration in minutes")
    timezone: str = Field("America/New_York", description="IANA timezone")


class CheckAvailabilityArgs(BaseModel):
    """Arguments for the check_availability tool."""
    date: str = Field(..., description="Date to check")
    time: str = Field(..., description="Time to check")
    duration_minutes: int = Field(30, ge=5, le=480, description="Duration in minutes")


class AvailableSlotsArgs(BaseModel):
    """Arguments for the get_available_slots tool."""
    date: str = Field("tomorrow", description="Date to find slots for")
    preferred_period: str = Field(
        "any",
        description="Preferred time: 'morning', 'afternoon', 'evening', or 'any'",
        pattern="^(morning|afternoon|evening|any)$",
    )


# ──────────────────────────────────────────────
# Direct API Schemas
# ──────────────────────────────────────────────

class DirectScheduleRequest(BaseModel):
    """Schema for the direct /api/direct/schedule endpoint."""
    name: str = Field(..., min_length=1, description="Caller's name")
    date: str = Field(..., min_length=1, description="Meeting date")
    time: str = Field(..., min_length=1, description="Meeting time")
    title: Optional[str] = Field(None, description="Meeting title")
    duration_minutes: int = Field(30, ge=5, le=480, description="Duration in minutes")


# ──────────────────────────────────────────────
# Response Schemas
# ──────────────────────────────────────────────

class BookingRecord(BaseModel):
    """A single booking record from the database."""
    id: int
    caller_name: str
    meeting_title: Optional[str]
    scheduled_date: str
    scheduled_time: str
    duration_minutes: int
    timezone: str
    google_event_id: Optional[str]
    google_event_link: Optional[str]
    status: str
    created_at: str


class BookingsResponse(BaseModel):
    """Response for the bookings list endpoint."""
    bookings: list[BookingRecord]
    count: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    agent: str
    calendar_connected: bool
    timestamp: str


class EventCreatedResponse(BaseModel):
    """Response when an event is successfully created."""
    status: str = "created"
    event: dict


class ConflictResponse(BaseModel):
    """Response when a scheduling conflict is detected."""
    status: str = "conflict"
    conflicts: list[dict]
