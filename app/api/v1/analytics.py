"""Analytics: series and overview KPIs."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from sqlalchemy import func
from fastapi import APIRouter, HTTPException, status, Query

from app.dependencies import CurrentUser, CurrentWorkspace, DbSession
from app.db.models.series import Series
from app.db.models.episode import Episode
from app.db.models.post import Post
from app.db.models.social_account import SocialAccount
from app.db.models.credit_transaction import CreditTransaction

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _start_of_month(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)


@router.get("/series/{id}")
def series_analytics(
    id: UUID,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
    startDate: Optional[str] = Query(None),
    endDate: Optional[str] = Query(None),
):
    """Aggregates posts count and by-platform stats for a series. Views/likes require platform webhooks."""
    s = (
        db.query(Series)
        .filter(Series.id == id, Series.workspace_id == workspace.id)
        .first()
    )
    if not s:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Series not found")
    posted = (
        db.query(func.count(Post.id))
        .join(Episode, Post.episode_id == Episode.id)
        .filter(Episode.series_id == id, Post.status == "posted")
        .scalar()
    ) or 0
    # Per-platform: posts count (views/likes would come from platform APIs or webhooks)
    by_platform_q = (
        db.query(SocialAccount.platform, func.count(Post.id).label("posts_count"))
        .join(Post, Post.social_account_id == SocialAccount.id)
        .join(Episode, Post.episode_id == Episode.id)
        .filter(Episode.series_id == id, Post.status == "posted", SocialAccount.workspace_id == workspace.id)
        .group_by(SocialAccount.platform)
    )
    by_platform = [
        {"platform": row.platform, "postsCount": row.posts_count, "views": 0, "likes": 0}
        for row in by_platform_q.all()
    ]
    return {
        "seriesId": str(id),
        "views": 0,
        "likes": 0,
        "ctr": 0.0,
        "postsCount": posted,
        "byPlatform": by_platform,
    }


@router.get("/overview")
def overview(
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    """Workspace-level KPIs for dashboard."""
    now = datetime.now(timezone.utc)
    month_start = _start_of_month(now)
    total_episodes = (
        db.query(func.count(Episode.id))
        .join(Series, Episode.series_id == Series.id)
        .filter(Series.workspace_id == workspace.id)
        .scalar()
    ) or 0
    active_series = (
        db.query(func.count(Series.id))
        .filter(Series.workspace_id == workspace.id, Series.status.in_(["active", "running"]))
        .scalar()
    ) or 0
    # If status values differ, count all non-draft/non-archived
    if active_series == 0:
        active_series = (
            db.query(func.count(Series.id)).filter(Series.workspace_id == workspace.id).scalar()
        ) or 0
    credits_used_this_month = (
        db.query(func.coalesce(func.sum(func.abs(CreditTransaction.amount)), 0))
        .filter(
            CreditTransaction.workspace_id == workspace.id,
            CreditTransaction.type == "generation",
            CreditTransaction.created_at >= month_start,
        )
        .scalar()
    ) or 0
    # Total views would require platform APIs or webhook-stored metrics
    total_posts = (
        db.query(func.count(Post.id))
        .join(Episode, Post.episode_id == Episode.id)
        .join(Series, Episode.series_id == Series.id)
        .filter(Series.workspace_id == workspace.id, Post.status == "posted")
        .scalar()
    ) or 0
    return {
        "totalViews": 0,
        "totalEpisodes": total_episodes,
        "activeSeries": int(active_series),
        "creditsUsedThisMonth": int(credits_used_this_month),
        "totalPosts": int(total_posts),
    }
