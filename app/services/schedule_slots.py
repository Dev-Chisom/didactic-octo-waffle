"""Shared helpers for computing future publish slots from a series schedule."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo


def _parse_time(s: str) -> tuple[int, int]:
    """Parse 'HH:MM' or 'HH:MM:SS' to (hour, minute)."""
    parts = (s or "09:00").strip().split(":")
    h = int(parts[0]) if parts else 9
    m = int(parts[1]) if len(parts) > 1 else 0
    return h, m


def _parse_start_date(start_date: Any) -> Optional[datetime]:
    """Parse startDate from schedule (string or datetime) to timezone-aware datetime."""
    if start_date is None:
        return None
    if isinstance(start_date, datetime):
        if start_date.tzinfo is None:
            return start_date.replace(tzinfo=timezone.utc)
        return start_date
    if isinstance(start_date, str):
        try:
            from dateutil import parser as dateutil_parser
            parsed = dateutil_parser.parse(start_date)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except Exception:
            return None
    return None


def get_next_publish_slots(
    schedule: Optional[dict],
    count: int = 7,
) -> list[datetime]:
    """
    Return the next `count` publish times in UTC from a series schedule dict.
    schedule: { frequency?, publishTime?, timezone?, startDate?, customDays? }
    """
    schedule = schedule or {}
    frequency = schedule.get("frequency", "daily")
    publish_time = schedule.get("publishTime", "09:00")
    tz_name = schedule.get("timezone", "UTC")
    start_date = _parse_start_date(schedule.get("startDate"))
    custom_days = schedule.get("customDays")

    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    now = datetime.now(timezone.utc)
    start = start_date.astimezone(tz) if start_date and start_date.tzinfo else now.astimezone(tz)
    if start < now.astimezone(tz):
        start = now.astimezone(tz)
    hour, minute = _parse_time(publish_time)
    slots = []
    day_offset = 0
    max_days = 365
    while len(slots) < count and day_offset < max_days:
        candidate = start.replace(hour=hour, minute=minute, second=0, microsecond=0) + timedelta(days=day_offset)
        if candidate < now.astimezone(tz):
            day_offset += 1
            continue
        if frequency == "daily":
            slots.append(candidate.astimezone(timezone.utc))
        elif frequency == "weekly":
            if custom_days is not None and len(custom_days) > 0:
                if candidate.weekday() in custom_days:
                    slots.append(candidate.astimezone(timezone.utc))
            else:
                slots.append(candidate.astimezone(timezone.utc))
        else:
            slots.append(candidate.astimezone(timezone.utc))
        day_offset += 1
    return slots[:count]
