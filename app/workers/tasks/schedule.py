"""Episode scheduling: create upcoming episodes from series schedule, enqueue generate_script 6h before publish."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.db.models.episode import Episode
from app.db.models.series import Series
from app.workers.celery_app import celery_app
from app.workers.tasks.script import generate_script


def _parse_time(s: str) -> tuple[int, int]:
    """Parse 'HH:MM' or 'HH:MM:SS' to (hour, minute)."""
    parts = (s or "09:00").strip().split(":")
    h = int(parts[0]) if parts else 9
    m = int(parts[1]) if len(parts) > 1 else 0
    return h, m


def _next_slots(
    frequency: str,
    custom_days: list[int] | None,
    publish_time: str,
    tz_name: str,
    start_date: datetime | None,
    count: int,
) -> list[datetime]:
    """
    Return next `count` publish times in UTC.
    frequency: daily, weekly, custom
    custom_days: 0=Mon..6=Sun for weekly/custom
    publish_time: "09:00"
    tz_name: "America/New_York"
    """
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


@celery_app.task
def schedule_upcoming_episodes(series_id: str):
    """
    Compute upcoming publish slots from series schedule; create Episode rows
    for slots that don't have one; enqueue generate_script 6 hours before each scheduled_at.
    """
    db: Session = SessionLocal()
    try:
        series = db.query(Series).filter(Series.id == uuid.UUID(series_id)).first()
        if not series:
            return {"series_id": series_id, "scheduled": 0, "error": "Series not found"}

        schedule = series.schedule or {}
        if not schedule.get("active", True):
            return {"series_id": series_id, "scheduled": 0}

        frequency = schedule.get("frequency", "daily")
        publish_time = schedule.get("publishTime", "09:00")
        tz_name = schedule.get("timezone", "UTC")
        start_date = schedule.get("startDate")
        custom_days = schedule.get("customDays")
        if isinstance(start_date, str):
            try:
                from dateutil import parser as dateutil_parser
                start_date = dateutil_parser.parse(start_date)
                if start_date.tzinfo is None:
                    start_date = start_date.replace(tzinfo=timezone.utc)
            except Exception:
                start_date = None

        # Next 14 slots
        slots = _next_slots(
            frequency=frequency,
            custom_days=custom_days,
            publish_time=publish_time,
            tz_name=tz_name,
            start_date=start_date,
            count=14,
        )

        existing_dates = set()
        for e in db.query(Episode).filter(Episode.series_id == series.id).all():
            if e.scheduled_at:
                d = e.scheduled_at.date() if hasattr(e.scheduled_at, "date") else e.scheduled_at
                existing_dates.add(d)
        max_seq = db.query(Episode).filter(Episode.series_id == series.id).count()
        created = 0

        for slot_utc in slots:
            slot_date = slot_utc.date() if hasattr(slot_utc, "date") else slot_utc
            if slot_date in existing_dates:
                continue
            existing_dates.add(slot_date)
            max_seq += 1
            ep = Episode(
                id=uuid.uuid4(),
                series_id=series.id,
                sequence_number=max_seq,
                scheduled_at=slot_utc,
                status="scheduled",
            )
            db.add(ep)
            db.flush()
            created += 1
            eta = slot_utc - timedelta(hours=6)
            if eta > datetime.now(timezone.utc):
                generate_script.apply_async(args=[str(ep.id)], eta=eta)
            else:
                generate_script.delay(str(ep.id))

        db.commit()
        return {"series_id": series_id, "scheduled": created}
    finally:
        db.close()
