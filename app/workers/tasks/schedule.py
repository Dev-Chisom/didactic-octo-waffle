"""Episode scheduling: create upcoming episodes from series schedule, enqueue generate_script 6h before publish."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.db.models.episode import Episode
from app.db.models.series import Series
from app.services.schedule_slots import get_next_publish_slots
from app.workers.celery_app import celery_app
from app.workers.tasks.script import generate_script


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

        # Next 14 slots (shared logic with launch_series)
        slots = get_next_publish_slots(schedule, count=14)

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
