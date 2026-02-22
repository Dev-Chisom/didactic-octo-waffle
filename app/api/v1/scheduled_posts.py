"""Scheduled posts: upcoming episodes to be published."""

from datetime import datetime, timezone
from fastapi import APIRouter

from app.dependencies import CurrentUser, CurrentWorkspace, DbSession
from app.db.models.episode import Episode
from app.db.models.series import Series

router = APIRouter(prefix="/scheduled-posts", tags=["scheduled-posts"])


@router.get("")
def list_scheduled_posts(
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    """List upcoming scheduled episodes (scheduled_at in the future) with series info."""
    now = datetime.now(timezone.utc)
    rows = (
        db.query(Episode, Series.name)
        .join(Series, Episode.series_id == Series.id)
        .filter(
            Series.workspace_id == workspace.id,
            Episode.scheduled_at.isnot(None),
            Episode.scheduled_at > now,
        )
        .order_by(Episode.scheduled_at.asc())
        .limit(100)
        .all()
    )
    return [
        {
            "episodeId": str(ep.id),
            "seriesId": str(ep.series_id),
            "seriesName": name,
            "episodeNumber": ep.sequence_number,
            "scheduledAt": ep.scheduled_at.isoformat() if ep.scheduled_at else None,
        }
        for ep, name in rows
    ]
