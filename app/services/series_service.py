"""Series CRUD and wizard step updates."""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.db.models.series import Series
from app.db.models.episode import Episode, Script
from app.db.models.workspace import Workspace
from app.services.credits_service import estimate_credits_per_episode
from app.services.schedule_slots import get_next_publish_slots


def create_series(
    db: Session,
    workspace_id: uuid.UUID,
    name: Optional[str] = None,
    content_type: str = "motivation",
    custom_topic: Optional[dict] = None,
) -> Series:
    """Create a draft series (Step 1 minimal)."""
    series = Series(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        name=name or "Untitled Series",
        content_type=content_type,
        custom_topic=custom_topic,
        status="draft",
    )
    db.add(series)
    db.commit()
    db.refresh(series)
    return series


def list_series(db: Session, workspace_id: uuid.UUID) -> list[Series]:
    """List all series for a workspace, newest first."""
    return (
        db.query(Series)
        .filter(Series.workspace_id == workspace_id)
        .order_by(Series.updated_at.desc())
        .all()
    )


def get_series(db: Session, series_id: uuid.UUID, workspace_id: uuid.UUID) -> Optional[Series]:
    """Get series by id if it belongs to workspace."""
    return (
        db.query(Series)
        .filter(Series.id == series_id, Series.workspace_id == workspace_id)
        .first()
    )


def _apply_json_update(current: Optional[dict], payload: dict) -> dict:
    out = dict(current or {})
    for k, v in payload.items():
        if v is not None:
            out[k] = v
    return out


def update_step_1(
    db: Session,
    series: Series,
    name: Optional[str] = None,
    content_type: Optional[str] = None,
    custom_topic: Optional[dict] = None,
) -> Series:
    if name is not None:
        series.name = name
    if content_type is not None:
        series.content_type = content_type
    if custom_topic is not None:
        series.custom_topic = custom_topic
    db.commit()
    db.refresh(series)
    return series


def update_step_2(db: Session, series: Series, payload: dict) -> Series:
    series.script_preferences = _apply_json_update(series.script_preferences, payload)
    series.estimated_credits_per_video = estimate_credits_per_episode(series)
    db.commit()
    db.refresh(series)
    return series


def update_step_3(db: Session, series: Series, payload: dict) -> Series:
    series.voice_language = _apply_json_update(series.voice_language, payload)
    series.estimated_credits_per_video = estimate_credits_per_episode(series)
    db.commit()
    db.refresh(series)
    return series


def update_step_4(db: Session, series: Series, payload: dict) -> Series:
    # Convert UUIDs to str for JSON
    p = dict(payload)
    if p.get("libraryTrackId") is not None:
        p["libraryTrackId"] = str(p["libraryTrackId"])
    if p.get("customUploadAssetId") is not None:
        p["customUploadAssetId"] = str(p["customUploadAssetId"])
    series.music_settings = _apply_json_update(series.music_settings, p)
    db.commit()
    db.refresh(series)
    return series


def update_step_5(db: Session, series: Series, payload: dict) -> Series:
    series.art_style = _apply_json_update(series.art_style, payload)
    series.estimated_credits_per_video = estimate_credits_per_episode(series)
    db.commit()
    db.refresh(series)
    return series


def update_step_6(db: Session, series: Series, payload: dict) -> Series:
    series.caption_style = _apply_json_update(series.caption_style, payload)
    db.commit()
    db.refresh(series)
    return series


def update_step_7(db: Session, series: Series, effects: Optional[list[dict]]) -> Series:
    if effects is not None:
        series.visual_effects = [e.model_dump() if hasattr(e, "model_dump") else e for e in effects]
    series.estimated_credits_per_video = estimate_credits_per_episode(series)
    db.commit()
    db.refresh(series)
    return series


def update_step_8(db: Session, series: Series, social_account_ids: Optional[list[uuid.UUID]]) -> Series:
    if social_account_ids is not None:
        series.connected_social_account_ids = [str(x) for x in social_account_ids]
    db.commit()
    db.refresh(series)
    return series


def update_step_9(db: Session, series: Series, payload: dict) -> Series:
    series.schedule = _apply_json_update(series.schedule, payload)
    db.commit()
    db.refresh(series)
    return series


def launch_series(
    db: Session,
    series: Series,
    workspace: Workspace,
) -> tuple[Series, list[dict], dict]:
    """
    Validate series, schedule first batch of episodes, return (series, upcoming_episodes, credit_estimate).
    """
    if series.status not in ("draft", "paused"):
        raise ValueError("Series cannot be launched in current state")
    # Simple validation: required steps present
    if not series.script_preferences or not series.voice_language:
        raise ValueError("Complete required wizard steps before launch")
    credit_per = estimate_credits_per_episode(series)
    balance = workspace.credits_balance or 0
    schedule = series.schedule or {}
    frequency = schedule.get("frequency", "daily")
    # Schedule next 7 episodes at future publish slots (so they show on Scheduled posts)
    slots = get_next_publish_slots(schedule, count=7)
    upcoming = []
    for i, slot_utc in enumerate(slots, start=1):
        ep = Episode(
            id=uuid.uuid4(),
            series_id=series.id,
            sequence_number=i,
            scheduled_at=slot_utc,
            status="scheduled",
        )
        db.add(ep)
        upcoming.append({
            "id": str(ep.id),
            "sequenceNumber": ep.sequence_number,
            "scheduledAt": ep.scheduled_at.isoformat() if ep.scheduled_at else None,
            "status": ep.status,
        })
    series.status = "active"
    series.auto_post_enabled = bool(series.connected_social_account_ids)
    if schedule.get("active") is not None:
        pass  # already in schedule
    db.commit()
    db.refresh(series)
    return series, upcoming, {
        "perEpisode": credit_per,
        "estimatedMonthly": credit_per * (7 if frequency == "daily" else 12),
        "currentBalance": balance,
    }
