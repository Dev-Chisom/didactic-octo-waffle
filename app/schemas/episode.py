"""Episode and script schemas (camelCase for FE contract)."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class EpisodeResponse(BaseModel):
    """Episode as returned by API. camelCase for frontend contract."""

    id: UUID
    seriesId: UUID
    seriesName: Optional[str] = None
    episodeNumber: int
    title: Optional[str] = None
    script: Optional[str] = None
    status: str
    videoUrl: Optional[str] = None
    thumbnailUrl: Optional[str] = None
    publishedAt: Optional[datetime] = None
    createdAt: datetime
    updatedAt: datetime
    publishedPlatforms: Optional[list] = None
    views: Optional[int] = None
    engagement: Optional[dict] = None
