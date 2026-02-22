"""Episodes and content library."""

from uuid import UUID
from typing import Optional
from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy.orm import joinedload

from app.dependencies import CurrentUser, CurrentWorkspace, DbSession
from app.db.models.episode import Episode
from app.db.models.series import Series
from app.db.models.post import Post
from app.db.models.social_account import SocialAccount
from app.schemas.episode import EpisodeResponse
from app.services.generation_service import run_script_generation
from app.services.storage_service import get_download_url
from app.workers.tasks.post import post_to_platform
from app.workers.tasks.media import generate_media

router = APIRouter(prefix="/episodes", tags=["episodes"])


def _episode_to_response(ep: Episode, series_name: Optional[str] = None) -> EpisodeResponse:
    """Build episode response in camelCase for FE contract; preview URLs resolved for client access."""
    preview = get_download_url(ep.preview_url) if ep.preview_url else None
    return EpisodeResponse(
        id=ep.id,
        seriesId=ep.series_id,
        seriesName=series_name,
        episodeNumber=ep.sequence_number,
        title=f"Episode {ep.sequence_number}" if ep.sequence_number else None,
        script=ep.script.text if ep.script else None,
        status=ep.status,
        videoUrl=preview,
        thumbnailUrl=preview,
        publishedAt=None,
        createdAt=ep.created_at,
        updatedAt=ep.updated_at,
        publishedPlatforms=None,
        views=None,
        engagement=None,
    )


@router.get("", response_model=list[EpisodeResponse])
def list_episodes(
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
    seriesId: Optional[UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    dateRange: Optional[str] = None,
):
    """List episodes; filter by seriesId or status (e.g. status=generating). Includes script text when available."""
    q = (
        db.query(Episode)
        .join(Series, Episode.series_id == Series.id)
        .filter(Series.workspace_id == workspace.id)
        .options(joinedload(Episode.series), joinedload(Episode.script))
    )
    if seriesId:
        q = q.filter(Episode.series_id == seriesId)
    if status_filter:
        q = q.filter(Episode.status == status_filter)
    episodes = q.order_by(Episode.scheduled_at.desc().nullslast()).limit(100).all()
    return [_episode_to_response(e, series_name=e.series.name if e.series else None) for e in episodes]


@router.get("/{id}", response_model=EpisodeResponse)
def get_episode(
    id: UUID,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    """Get one episode with series name and generated script text."""
    ep = (
        db.query(Episode)
        .join(Series, Episode.series_id == Series.id)
        .filter(Series.workspace_id == workspace.id, Episode.id == id)
        .options(joinedload(Episode.series), joinedload(Episode.script))
        .first()
    )
    if not ep:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    return _episode_to_response(ep, series_name=ep.series.name if ep.series else None)


@router.post("/{episode_id}/generate")
def generate_episode(
    episode_id: UUID,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    """
    Generate script for this episode (LLM). Runs synchronously.
    Episode must be in status 'scheduled' or 'failed'. Sets status to 'ready_for_review' on success.
    Video generation (media + render) is not yet implemented; only the script is produced.
    """
    ep = (
        db.query(Episode)
        .join(Series, Episode.series_id == Series.id)
        .filter(Series.workspace_id == workspace.id, Episode.id == episode_id)
        .first()
    )
    if not ep:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    if ep.status not in ("scheduled", "failed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Episode cannot be generated in current state (status: {ep.status})",
        )
    try:
        result = run_script_generation(db, episode_id)
        return {"success": True, "message": "Script generated", **result}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Script generation failed: " + str(e),
        )


@router.post("/{episode_id}/generate-media")
def trigger_generate_media(
    episode_id: UUID,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    """
    Enqueue media generation (TTS + assets) then render for this episode.
    Episode must have a script (status ready_for_review or generating). Returns immediately; video appears when Celery worker finishes.
    """
    ep = (
        db.query(Episode)
        .join(Series, Episode.series_id == Series.id)
        .filter(Series.workspace_id == workspace.id, Episode.id == episode_id)
        .options(joinedload(Episode.script))
        .first()
    )
    if not ep:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    if not ep.script_id or not ep.script:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Generate a script first (POST /episodes/{id}/generate)",
        )
    if ep.status not in ("ready_for_review", "generating", "failed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Episode not ready for video (status: {ep.status})",
        )
    generate_media.delay(str(ep.id))
    return {"success": True, "message": "Video generation started. Refresh to see status and video URL when ready."}


@router.post("/{episode_id}/publish-now")
def publish_now(
    episode_id: UUID,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    """Create Post rows for each connected account and enqueue post_to_platform tasks."""
    ep = (
        db.query(Episode)
        .join(Series, Episode.series_id == Series.id)
        .filter(Series.workspace_id == workspace.id, Episode.id == episode_id)
        .options(joinedload(Episode.series))
        .first()
    )
    if not ep:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    if not ep.video_asset_id or not ep.preview_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Episode has no video; generate script, then media, then render first",
        )

    series = ep.series
    # Resolve target accounts: series.connected_social_account_ids or all workspace connected
    account_ids = list(series.connected_social_account_ids or []) if series else []
    if not account_ids:
        accounts = (
            db.query(SocialAccount)
            .filter(SocialAccount.workspace_id == workspace.id, SocialAccount.status == "connected")
            .all()
        )
        account_ids = [str(a.id) for a in accounts]
    else:
        try:
            uuids = [UUID(aid) for aid in account_ids if aid]
        except (ValueError, TypeError):
            uuids = []
        accounts = (
            db.query(SocialAccount)
            .filter(
                SocialAccount.workspace_id == workspace.id,
                SocialAccount.id.in_(uuids),
                SocialAccount.status == "connected",
            )
            .all()
        )
        account_ids = [str(a.id) for a in accounts]

    if not account_ids:
        return {"success": False, "message": "No connected accounts to publish to", "publishedAt": None}

    created = []
    for social_account_id in account_ids:
        post = Post(
            episode_id=ep.id,
            social_account_id=UUID(social_account_id),
            status="pending",
        )
        db.add(post)
        db.flush()
        created.append(post.id)
        post_to_platform.delay(str(post.id))

    db.commit()
    return {"success": True, "postsEnqueued": len(created), "postIds": [str(p) for p in created], "publishedAt": None}
