"""
Tool API Routes — /tools/api/v1/
=================================
VAPI server-url tool endpoints. These are the "hands" of Aria —
when the LLM decides to take an action, VAPI calls these endpoints.

All tool endpoints follow the same contract:
  Input:  VAPI tool call payload
  Output: VAPI tool result with natural language response
"""

import datetime
import traceback
import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from dateutil import parser as date_parser

from app.config import settings
from app.models import ScheduleEventArgs, CheckAvailabilityArgs, AvailableSlotsArgs, DirectScheduleRequest
from app.calendar_service import calendar_service
from app.database import log_booking
from app.datetime_utils import parse_datetime
from app.vapi_utils import extract_tool_call, tool_response

router = APIRouter(prefix="/tools/api/v1", tags=["tools"])


@router.post("/schedule-event")
async def schedule_event(request: Request):
    """Create a calendar event — called by Aria after user confirmation."""
    body = await request.json()
    tc = extract_tool_call(body)
    if not tc:
        return JSONResponse(content={"error": "Invalid tool call"}, status_code=400)

    raw_args = tc.get("function", {}).get("arguments", {})
    tc_id = tc.get("id", "")

    # Validate with Pydantic
    try:
        args = ScheduleEventArgs(**raw_args)
    except Exception:
        return tool_response(tc_id, "I couldn't understand the scheduling details. Could you repeat that?")

    # Auth check
    if not calendar_service.is_authenticated:
        return tool_response(tc_id,
            "I'm sorry, the calendar isn't connected yet. Please ask the administrator to set it up.")

    # Parse datetime
    try:
        start_time = parse_datetime(args.date, args.time, args.timezone)
        end_time = start_time + datetime.timedelta(minutes=args.duration_minutes)
    except ValueError:
        return tool_response(tc_id,
            "I couldn't quite understand that date or time. Could you say it once more?")

    # Check conflicts
    try:
        conflicts = await asyncio.to_thread(calendar_service.check_conflicts, start_time, end_time)
        if conflicts:
            conflict_name = conflicts[0].get("summary", "another event")
            return tool_response(tc_id,
                f"There's a conflict — you already have '{conflict_name}' at that time. Would you like to pick a different time?")
    except Exception as e:
        print(f"[Aria] Conflict check failed: {e}")

    # Create event with retry
    event_title = args.title or f"Meeting with {args.name}"
    for attempt in range(2):
        try:
            event = await asyncio.to_thread(calendar_service.create_event,
                summary=event_title,
                start_time=start_time,
                end_time=end_time,
                attendee_name=args.name,
                description=f"Scheduled by {args.name} via Aria Voice Agent",
                timezone=args.timezone,
            )

            # Log to database
            try:
                await asyncio.to_thread(log_booking,
                    caller_name=args.name,
                    meeting_title=event_title,
                    scheduled_date=start_time.strftime("%Y-%m-%d"),
                    scheduled_time=start_time.strftime("%I:%M %p"),
                    duration_minutes=args.duration_minutes,
                    timezone=args.timezone,
                    google_event_id=event["id"],
                    google_event_link=event["htmlLink"],
                )
            except Exception as log_err:
                print(f"[Aria] Booking log failed: {log_err}")

            formatted_date = start_time.strftime("%A, %B %d at %I:%M %p")
            return tool_response(tc_id,
                f"Done! '{event_title}' is confirmed for {formatted_date}. It's on your Google Calendar. Is there anything else I can help with?")

        except Exception as e:
            print(f"[Aria] Event creation attempt {attempt + 1} failed: {e}")
            if attempt == 0:
                continue
            return tool_response(tc_id,
                "I'm having a small technical hiccup with the calendar. Could we try a different time, or would you like me to try again?")


@router.post("/check-availability")
async def check_availability(request: Request):
    """Check if a time slot is available."""
    body = await request.json()
    tc = extract_tool_call(body)
    if not tc:
        return JSONResponse(content={"error": "Invalid tool call"}, status_code=400)

    raw_args = tc.get("function", {}).get("arguments", {})
    tc_id = tc.get("id", "")

    try:
        args = CheckAvailabilityArgs(**raw_args)
    except Exception:
        return tool_response(tc_id, "I couldn't understand that. Could you try again?")

    if not calendar_service.is_authenticated:
        return tool_response(tc_id, "Calendar not connected.")

    try:
        start_time = parse_datetime(args.date, args.time)
        end_time = start_time + datetime.timedelta(minutes=args.duration_minutes)
        conflicts = await asyncio.to_thread(calendar_service.check_conflicts, start_time, end_time)

        if conflicts:
            conflict_name = conflicts[0].get("summary", "another event")
            return tool_response(tc_id,
                f"That slot isn't available — there's '{conflict_name}' at that time. Would you like to try a different time, or should I check what's open?")

        formatted = start_time.strftime("%A, %B %d at %I:%M %p")
        return tool_response(tc_id, f"{formatted} is available! Shall I go ahead and book it?")

    except ValueError:
        return tool_response(tc_id, "I couldn't understand that date or time. Could you try again?")
    except Exception as e:
        print(f"[Aria] Availability check error: {e}")
        return tool_response(tc_id,
            "I'm having trouble checking the calendar right now. Could you give me the time and I'll try to book it directly?")


@router.post("/available-slots")
async def available_slots(request: Request):
    """Find available time slots for a given date."""
    body = await request.json()
    tc = extract_tool_call(body)
    if not tc:
        return JSONResponse(content={"error": "Invalid tool call"}, status_code=400)

    raw_args = tc.get("function", {}).get("arguments", {})
    tc_id = tc.get("id", "")

    try:
        args = AvailableSlotsArgs(**raw_args)
    except Exception:
        return tool_response(tc_id, "I couldn't understand that. Could you try again?")

    if not calendar_service.is_authenticated:
        return tool_response(tc_id, "Calendar not connected.")

    try:
        base_date = parse_datetime(args.date, "9:00 AM")

        period_ranges = {
            "morning":   (9, 12),
            "afternoon": (12, 17),
            "evening":   (17, 20),
            "any":       (9, 18),
        }
        start_h, end_h = period_ranges.get(args.preferred_period, (9, 18))
        search_start = base_date.replace(hour=start_h, minute=0)
        search_end = base_date.replace(hour=end_h, minute=0)

        events = await asyncio.to_thread(calendar_service.check_conflicts, search_start, search_end)

        # Build busy time ranges
        busy_times = []
        for evt in events:
            start = evt.get("start", {})
            end = evt.get("end", {})
            if "dateTime" in start:
                busy_times.append((
                    date_parser.parse(start["dateTime"]),
                    date_parser.parse(end["dateTime"]),
                ))
            elif "date" in start:
                return tool_response(tc_id,
                    f"It looks like you have an all-day event on {args.date}. Would you like to try a different day?")

        # Find gaps
        available = []
        current = search_start
        while current + datetime.timedelta(minutes=30) <= search_end and len(available) < 3:
            slot_end = current + datetime.timedelta(minutes=30)
            is_free = True
            for busy_start, busy_end in busy_times:
                if current < busy_end and slot_end > busy_start:
                    is_free = False
                    current = busy_end
                    break
            if is_free:
                available.append(current.strftime("%I:%M %p"))
                current += datetime.timedelta(minutes=60)
            elif current == slot_end:
                current += datetime.timedelta(minutes=30)

        if available:
            slots_str = ", ".join(available[:-1]) + f", or {available[-1]}" if len(available) > 1 else available[0]
            formatted_date = base_date.strftime("%A, %B %d")
            return tool_response(tc_id,
                f"On {formatted_date}, I have these slots open: {slots_str}. Which works best for you?")
        else:
            return tool_response(tc_id,
                f"It looks like {args.date} is pretty packed. Would you like to try a different day?")

    except Exception as e:
        print(f"[Aria] Available slots error: {e}\n{traceback.format_exc()}")
        return tool_response(tc_id,
            "I'm having trouble checking the schedule. Could you suggest a specific time and I'll see if it works?")
