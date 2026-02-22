"""Music presets, library, and custom upload."""

import uuid
from uuid import UUID
from typing import Optional
from fastapi import APIRouter, File, UploadFile, HTTPException, status, Query

from app.dependencies import CurrentUser, CurrentWorkspace, DbSession
from app.db.models.asset import Asset
from app.schemas.voice_music import MusicLibraryItem, MusicPresetItem
from app.services.storage_service import upload_file, music_upload_key, get_download_url
from app.config import get_settings

router = APIRouter(prefix="/music", tags=["music"])

ALLOWED_MUSIC_TYPES = {"audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/m4a"}
EXT_BY_CONTENT = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/m4a": ".m4a",
}


@router.get("/presets", response_model=list[MusicPresetItem])
def list_presets(
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    """Return mood categories + track samples."""
    return [
        MusicPresetItem(id="upbeat", mood="upbeat", name="Upbeat", sampleUrl=None),
        MusicPresetItem(id="calm", mood="calm", name="Calm", sampleUrl=None),
        MusicPresetItem(id="neutral", mood="neutral", name="Neutral", sampleUrl=None),
    ]


@router.get("/library", response_model=list[MusicLibraryItem])
def list_library(
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
    mood: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 20,
):
    """Paginated library of uploaded music assets, optional filter by mood."""
    q = (
        db.query(Asset)
        .filter(Asset.workspace_id == workspace.id, Asset.type == "music")
        .order_by(Asset.created_at.desc())
    )
    items = q.offset(skip).limit(limit * 2 if mood else limit).all()
    if mood:
        items = [a for a in items if (a.metadata_ or {}).get("mood") == mood][:limit]
    return [
        MusicLibraryItem(
            id=a.id,
            mood=(a.metadata_ or {}).get("mood", "custom"),
            name=(a.metadata_ or {}).get("name", "Custom track"),
            durationSeconds=float(a.duration_seconds or 0),
            url=get_download_url(a.url) if a.url else None,
        )
        for a in items
    ]


@router.post("/upload")
def upload(
    user: CurrentUser,
    workspace: CurrentWorkspace,
    db: DbSession,
    file: UploadFile = File(...),
):
    """Custom music upload; uploads to S3, creates Asset and returns id/url."""
    settings = get_settings()
    content_type = (file.content_type or "").lower()
    if not content_type and file.filename:
        if file.filename.lower().endswith(".mp3"):
            content_type = "audio/mpeg"
        elif file.filename.lower().endswith(".wav"):
            content_type = "audio/wav"
        elif file.filename.lower().endswith(".m4a"):
            content_type = "audio/m4a"
    if content_type not in ALLOWED_MUSIC_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Allowed: mp3, wav, m4a",
        )
    asset_id = uuid.uuid4()
    ext = EXT_BY_CONTENT.get(content_type, ".mp3")
    key = music_upload_key(workspace.id, asset_id, ext)

    if settings.aws_access_key_id and settings.aws_secret_access_key:
        url = upload_file(key, file.file, content_type)
    else:
        url = f"https://storage.example.com/music/{workspace.id}/{asset_id}"

    asset = Asset(
        id=asset_id,
        workspace_id=workspace.id,
        type="music",
        source="uploaded",
        url=url,
        format=content_type or None,
        duration_seconds=None,
        metadata_={"name": file.filename or "Uploaded track", "mood": "custom"},
    )
    db.add(asset)
    db.commit()
    return {"id": str(asset.id), "url": get_download_url(asset.url)}


@router.delete("/{id}")
def delete_track(
    id: UUID,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    """Delete a music asset from the library."""
    asset = (
        db.query(Asset)
        .filter(Asset.id == id, Asset.workspace_id == workspace.id, Asset.type == "music")
        .first()
    )
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Music track not found")
    db.delete(asset)
    db.commit()
    return {"ok": True}
