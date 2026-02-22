"""Episode and Script models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.series import Series
    from app.db.models.post import Post


class Episode(Base):
    __tablename__ = "episodes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    series_id: Mapped[uuid.UUID] = mapped_column(
        "seriesId",
        UUID(as_uuid=True),
        ForeignKey("series.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column("sequenceNumber", Integer, nullable=False)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(
        "scheduledAt",
        DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="scheduled",
        nullable=False,
    )  # scheduled, generating, ready_for_review, approved, posted, failed
    script_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        "scriptId",
        UUID(as_uuid=True),
        ForeignKey("scripts.id", ondelete="SET NULL"),
        nullable=True,
    )
    video_asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        "videoAssetId",
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    preview_url: Mapped[Optional[str]] = mapped_column("previewUrl", String(2048), nullable=True)
    error: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    credits_used: Mapped[float] = mapped_column("creditsUsed", Float, default=0)
    created_at: Mapped[datetime] = mapped_column(
        "createdAt",
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        "updatedAt",
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    series: Mapped["Series"] = relationship(
        "Series", back_populates="episodes", foreign_keys=[series_id]
    )
    script: Mapped[Optional["Script"]] = relationship(
        "Script", back_populates="episode", foreign_keys=[script_id]
    )
    posts: Mapped[List["Post"]] = relationship("Post", back_populates="episode")


class Script(Base):
    __tablename__ = "scripts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    series_id: Mapped[uuid.UUID] = mapped_column(
        "seriesId",
        UUID(as_uuid=True),
        ForeignKey("series.id", ondelete="CASCADE"),
        nullable=False,
    )
    language_code: Mapped[str] = mapped_column("languageCode", String(20), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    scenes: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSONB, nullable=True)
    prompt_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "promptMetadata",
        JSONB,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        "createdAt",
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    episode: Mapped[Optional["Episode"]] = relationship(
        "Episode",
        back_populates="script",
        primaryjoin="Script.id == Episode.script_id",
        foreign_keys="Episode.script_id",
        viewonly=True,
        uselist=False,
    )
