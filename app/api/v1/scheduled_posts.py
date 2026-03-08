"""Scheduled posts: upcoming and (optionally) past scheduled episodes."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query

from app.dependencies import CurrentUser, CurrentWorkspace, DbSession
from app.db.models.episode import Episode
from app.db.models.series import Series

router = APIRouter(prefix="/scheduled-posts", tags=["scheduled-posts"])


@router.get("")
def list_scheduled_posts(
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
    include_past: bool = Query(False, alias="includePast", description="Include episodes whose scheduled time has passed"),
):
    """
    List scheduled episodes with series info.

    By default returns only upcoming (scheduled_at in the future). Use includePast=true
    to also return past-due episodes so you can see what was scheduled and their status
    (e.g. posted, ready_for_review, failed). Past episodes are not deleted; they just
    drop off the default list once their slot has passed.
    """
    now = datetime.now(timezone.utc)
    q = (
        db.query(Episode, Series.name)
        .join(Series, Episode.series_id == Series.id)
        .filter(
            Series.workspace_id == workspace.id,
            Episode.scheduled_at.isnot(None),
        )
    )
    if not include_past:
        q = q.filter(Episode.scheduled_at > now)
    rows = q.order_by(Episode.scheduled_at.asc()).limit(100).all()
    return [
        {
            "episodeId": str(ep.id),
            "seriesId": str(ep.series_id),
            "seriesName": name,
            "episodeNumber": ep.sequence_number,
            "scheduledAt": ep.scheduled_at.isoformat() if ep.scheduled_at else None,
            "status": ep.status,
            "isPast": ep.scheduled_at <= now if ep.scheduled_at else False,
        }
        for ep, name in rows
    ]
