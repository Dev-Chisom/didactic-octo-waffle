"""Content library: list assets (music, video, etc.) by workspace."""

from typing import Optional
from fastapi import APIRouter, Query

from app.dependencies import CurrentUser, CurrentWorkspace, DbSession
from app.db.models.asset import Asset
from app.schemas.asset import asset_to_response

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("")
def list_assets(
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
    type: Optional[str] = Query(None, description="Filter by type: music, video, audio, image"),
    skip: int = 0,
    limit: int = 50,
):
    """List workspace assets for content library. Optional type filter."""
    q = db.query(Asset).filter(Asset.workspace_id == workspace.id).order_by(Asset.created_at.desc())
    if type:
        types = [t.strip() for t in type.split(",") if t.strip()]
        if types:
            q = q.filter(Asset.type.in_(types))
    items = q.offset(skip).limit(limit).all()
    return [asset_to_response(a) for a in items]
