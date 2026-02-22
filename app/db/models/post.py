"""Post model for platform publish records."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.episode import Episode
    from app.db.models.social_account import SocialAccount


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    episode_id: Mapped[uuid.UUID] = mapped_column(
        "episodeId",
        UUID(as_uuid=True),
        ForeignKey("episodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    social_account_id: Mapped[uuid.UUID] = mapped_column(
        "socialAccountId",
        UUID(as_uuid=True),
        ForeignKey("social_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    platform_post_id: Mapped[Optional[str]] = mapped_column(
        "platformPostId",
        String(255),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
    )  # pending, posting, posted, failed
    error: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    posted_at: Mapped[Optional[datetime]] = mapped_column(
        "postedAt",
        DateTime(timezone=True),
        nullable=True,
    )

    episode: Mapped["Episode"] = relationship(
        "Episode", back_populates="posts", foreign_keys=[episode_id]
    )
    social_account: Mapped["SocialAccount"] = relationship(
        "SocialAccount", back_populates="posts", foreign_keys=[social_account_id]
    )
