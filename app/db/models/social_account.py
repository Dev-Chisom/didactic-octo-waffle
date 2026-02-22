"""SocialAccount model for connected platforms."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.workspace import Workspace
    from app.db.models.post import Post


class SocialAccount(Base):
    __tablename__ = "social_accounts"

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
    platform: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )  # tiktok, instagram, youtube, facebook
    display_name: Mapped[Optional[str]] = mapped_column("displayName", String(255), nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column("avatarUrl", String(2048), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default="connected",
        nullable=False,
    )  # connected, expired, error, limited
    access_token: Mapped[Optional[str]] = mapped_column(
        "accessToken",
        Text,
        nullable=True,
    )  # encrypted at rest
    refresh_token: Mapped[Optional[str]] = mapped_column(
        "refreshToken",
        Text,
        nullable=True,
    )
    scopes: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        "expiresAt",
        DateTime(timezone=True),
        nullable=True,
    )
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
        "Workspace", backref="social_accounts", foreign_keys=[workspace_id]
    )
    posts: Mapped[List["Post"]] = relationship("Post", back_populates="social_account")
