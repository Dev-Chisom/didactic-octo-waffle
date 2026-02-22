"""Asset (content library) schemas."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID
from pydantic import BaseModel

from app.services.storage_service import get_download_url


class AssetResponse(BaseModel):
    id: UUID
    type: str
    source: str
    url: str
    format: Optional[str] = None
    durationSeconds: Optional[float] = None
    metadata: Optional[dict[str, Any]] = None
    createdAt: datetime

    model_config = {"from_attributes": True}


def asset_to_response(asset) -> dict:
    """Map ORM Asset to response; URL is resolved for client access (presigned if private S3)."""
    return {
        "id": asset.id,
        "type": asset.type,
        "source": asset.source,
        "url": get_download_url(asset.url) if asset.url else "",
        "format": asset.format,
        "durationSeconds": asset.duration_seconds,
        "metadata": asset.metadata_,
        "createdAt": asset.created_at,
    }
