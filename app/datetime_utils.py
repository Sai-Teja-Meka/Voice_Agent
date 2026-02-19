"""
Date/Time Utilities
====================
Natural language date/time parsing with timezone awareness.
Handles: 'tomorrow', 'next Monday', 'February 20th', '3pm', 'noon', etc.
"""

import datetime
from dateutil import parser as date_parser
from dateutil import tz as dateutil_tz

from app.config import settings


def parse_datetime(date_str: str, time_str: str, timezone: str = None) -> datetime.datetime:
    """
    Parse natural language date/time into a timezone-aware datetime.

    Args:
        date_str: Date in natural language or ISO format
        time_str: Time in natural language or 24h format
        timezone: IANA timezone string (defaults to settings.DEFAULT_TIMEZONE)

    Returns:
        Timezone-aware datetime object

    Raises:
        ValueError: If date/time cannot be parsed
    """
    tz_str = timezone or settings.DEFAULT_TIMEZONE
    target_tz = dateutil_tz.gettz(tz_str)
    today = datetime.datetime.now(tz=target_tz)
    date_lower = date_str.strip().lower()

    # Handle common relative dates
    if date_lower in ("today",):
        base_date = today
    elif date_lower in ("tomorrow",):
        base_date = today + datetime.timedelta(days=1)
    else:
        try:
            base_date = date_parser.parse(date_str, fuzzy=True)
            # Don't schedule in the past
            if base_date.date() < today.date():
                candidate = base_date.replace(year=today.year)
                if candidate.date() < today.date():
                    candidate = base_date.replace(year=today.year + 1)
                base_date = candidate
        except Exception:
            base_date = today

    # Parse time component
    try:
        time_part = date_parser.parse(time_str, fuzzy=True)
        result = base_date.replace(
            hour=time_part.hour, minute=time_part.minute, second=0, microsecond=0
        )
    except Exception:
        try:
            combined = f"{date_str} {time_str}"
            result = date_parser.parse(combined, fuzzy=True)
        except Exception as e:
            raise ValueError(f"Could not parse: '{date_str} {time_str}'. Error: {e}")

    # Ensure timezone-aware
    if result.tzinfo is None:
        result = result.replace(tzinfo=target_tz)

    return result
