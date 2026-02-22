"""Series model with wizard config (content type, script, voice, music, art, captions, effects, schedule)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.workspace import Workspace
    from app.db.models.episode import Episode
    from app.db.models.social_account import SocialAccount


class Series(Base):
    __tablename__ = "series"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        "workspaceId",
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(
        "contentType",
        String(50),
        nullable=False,
    )  # motivation, horror, finance, ai_tech, kids, anime, custom
    custom_topic: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "customTopic",
        JSONB,
        nullable=True,
    )  # topicTitle, targetAudience, tone, keywords, ctaStyle

    # Script preferences (JSON)
    script_preferences: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "scriptPreferences",
        JSONB,
        nullable=True,
    )  # storyLength, tone, hookStrength, includeCta, ctaText

    # Voice & language (JSON)
    voice_language: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "voiceLanguage",
        JSONB,
        nullable=True,
    )  # languageCode, gender, style, speed, pitch

    # Music settings (JSON)
    music_settings: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "musicSettings",
        JSONB,
        nullable=True,
    )  # mode, presetMood, libraryTrackId, customUploadAssetId, tiktokUrl

    # Art style (JSON)
    art_style: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "artStyle",
        JSONB,
        nullable=True,
    )  # style, intensity, colorTheme

    # Caption style (JSON)
    caption_style: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "captionStyle",
        JSONB,
        nullable=True,
    )  # style, fontFamily, fontColor, highlightColor, position, backgroundEnabled

    # Visual effects (JSON list)
    visual_effects: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        "visualEffects",
        JSONB,
        nullable=True,
    )  # array of { type, enabled, isPremium, params }

    # Schedule (JSON)
    schedule: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "schedule",
        JSONB,
        nullable=True,
    )  # videoDuration, frequency, customDays, publishTime, timezone, startDate, active

    status: Mapped[str] = mapped_column(
        String(20),
        default="draft",
        nullable=False,
    )  # draft, active, paused, archived
    estimated_credits_per_video: Mapped[Optional[float]] = mapped_column(
        "estimatedCreditsPerVideo",
        Float,
        nullable=True,
    )
    auto_post_enabled: Mapped[bool] = mapped_column("autoPostEnabled", Boolean, default=False)
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

    workspace: Mapped["Workspace"] = relationship(
        "Workspace", back_populates="series", foreign_keys=[workspace_id]
    )
    episodes: Mapped[List["Episode"]] = relationship(
        "Episode", back_populates="series", order_by="Episode.sequence_number"
    )
    # Social accounts linked for auto-post (stored as JSON array of IDs for simplicity)
    connected_social_account_ids: Mapped[Optional[List]] = mapped_column(
        "connectedSocialAccountIds",
        JSONB,
        nullable=True,
    )
