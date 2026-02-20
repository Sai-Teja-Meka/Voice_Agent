"""
Date/Time Utilities
====================
Natural language date/time parsing with timezone awareness.
Handles: 'tomorrow', 'next Monday', 'February 20th', '3pm', 'noon', etc.
"""

import datetime
import parsedatetime
from dateutil import parser as date_parser
from dateutil import tz as dateutil_tz

from app.config import settings


def parse_datetime(date_str: str, time_str: str, timezone: str = None) -> datetime.datetime:
    """
    Parse natural language date/time into a timezone-aware datetime.
    Handles: 'tomorrow', 'in 3 days', 'next Tuesday', 'day after tomorrow',
    'next week', 'after five days', 'March 5th', '3pm', 'noon', etc.
    """
    
    tz_str = timezone or settings.DEFAULT_TIMEZONE
    target_tz = dateutil_tz.gettz(tz_str)
    now = datetime.datetime.now(tz=target_tz)
    
    cal = parsedatetime.Calendar()
    
    # Parse date using parsedatetime (handles all relative expressions)
    date_result, date_status = cal.parseDT(date_str, sourceTime=now, tzinfo=target_tz)
    if date_status == 0:
        # parsedatetime couldn't parse it, try dateutil as fallback
        try:
            date_result = date_parser.parse(date_str, fuzzy=True)
            if date_result.date() < now.date():
                candidate = date_result.replace(year=now.year)
                if candidate.date() < now.date():
                    candidate = date_result.replace(year=now.year + 1)
                date_result = candidate
        except Exception:
            date_result = now
    
    # Parse time
    try:
        time_result, time_status = cal.parseDT(time_str, sourceTime=now, tzinfo=target_tz)
        if time_status > 0:
            result = date_result.replace(
                hour=time_result.hour, minute=time_result.minute, second=0, microsecond=0
            )
        else:
            raise ValueError("parsedatetime failed")
    except Exception:
        try:
            time_part = date_parser.parse(time_str, fuzzy=True)
            result = date_result.replace(
                hour=time_part.hour, minute=time_part.minute, second=0, microsecond=0
            )
        except Exception:
            try:
                combined = f"{date_str} {time_str}"
                result, status = cal.parseDT(combined, sourceTime=now, tzinfo=target_tz)
                if status == 0:
                    raise ValueError("Failed")
            except Exception as e:
                raise ValueError(f"Could not parse: '{date_str} {time_str}'. Error: {e}")
    
    # Ensure timezone-aware
    if result.tzinfo is None:
        result = result.replace(tzinfo=target_tz)
    
    return result
