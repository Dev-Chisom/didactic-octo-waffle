"""Episode scheduling: create upcoming episodes, enqueue generate_script 6h before publish, and publish due episodes."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session, joinedload

from app.db.base import SessionLocal
from app.db.models.episode import Episode
from app.db.models.post import Post
from app.db.models.series import Series
from app.db.models.social_account import SocialAccount
from app.services.schedule_slots import get_next_publish_slots
from app.workers.celery_app import celery_app
from app.workers.tasks.script import generate_script
from app.workers.tasks.media import generate_media
from app.workers.tasks.post import post_to_platform


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


@celery_app.task
def backfill_orphaned_episodes():
    """
    Find episodes that need processing and queue the right task:
    1) Scheduled with no script → queue generate_script (chains generate_media)
    2) Script ready but no video → queue generate_media (e.g. from manual script gen or failed media)
    Runs periodically via Celery Beat.
    """
    db: Session = SessionLocal()
    queued_script = 0
    queued_media = 0
    try:
        # 1) Episodes with no script
        no_script = (
            db.query(Episode)
            .join(Series, Episode.series_id == Series.id)
            .filter(
                Episode.status == "scheduled",
                Episode.script_id.is_(None),
                Series.status == "active",
            )
            .limit(10)
            .all()
        )
        for ep in no_script:
            ep.status = "generating"
            generate_script.delay(str(ep.id))
            queued_script += 1

        # 2) Episodes with script but no video (e.g. manual script gen, or media failed)
        has_script_no_video = (
            db.query(Episode)
            .join(Series, Episode.series_id == Series.id)
            .filter(
                Episode.script_id.isnot(None),
                Episode.video_asset_id.is_(None),
                Episode.status.in_(("ready_for_review", "generating", "failed")),
                Series.status == "active",
            )
            .limit(10)
            .all()
        )
        for ep in has_script_no_video:
            ep.status = "generating"
            generate_media.delay(str(ep.id))
            queued_media += 1

        db.commit()
        return {"queued_script": queued_script, "queued_media": queued_media}
    finally:
        db.close()


@celery_app.task
def publish_due_episodes():
    """
    Publish episodes whose scheduled_at has passed, have video ready, and series has auto_post enabled.
    Runs periodically via Celery Beat (e.g. every 5 min).
    """
    db: Session = SessionLocal()
    now = datetime.now(timezone.utc)
    published = 0
    try:
        episodes = (
            db.query(Episode)
            .join(Series, Episode.series_id == Series.id)
            .filter(
                Episode.scheduled_at.isnot(None),
                Episode.scheduled_at <= now,
                Episode.video_asset_id.isnot(None),
                Episode.preview_url.isnot(None),
                Episode.status.in_(("ready_for_review", "approved")),
                Series.auto_post_enabled == True,
            )
            .options(joinedload(Episode.series), joinedload(Episode.posts))
            .all()
        )
        for ep in episodes:
            if ep.posts:
                continue
            series = ep.series
            account_ids = list(series.connected_social_account_ids or []) if series else []
            if not account_ids:
                accounts = (
                    db.query(SocialAccount)
                    .filter(
                        SocialAccount.workspace_id == series.workspace_id,
                        SocialAccount.status == "connected",
                    )
                    .all()
                )
                account_ids = [str(a.id) for a in accounts]
            else:
                try:
                    uuids = [uuid.UUID(aid) for aid in account_ids if aid]
                except (ValueError, TypeError):
                    uuids = []
                accounts = (
                    db.query(SocialAccount)
                    .filter(
                        SocialAccount.workspace_id == series.workspace_id,
                        SocialAccount.id.in_(uuids),
                        SocialAccount.status == "connected",
                    )
                    .all()
                )
                account_ids = [str(a.id) for a in accounts]
            if not account_ids:
                continue
            for social_account_id in account_ids:
                post = Post(
                    episode_id=ep.id,
                    social_account_id=uuid.UUID(social_account_id),
                    status="pending",
                )
                db.add(post)
                db.flush()
                post_to_platform.delay(str(post.id))
                published += 1
        db.commit()
        return {"published": published}
    finally:
        db.close()
