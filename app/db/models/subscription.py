"""Subscription model for Stripe billing."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.workspace import Workspace
    from app.db.models.plan import Plan


class Subscription(Base):
    __tablename__ = "subscriptions"

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
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        "stripeSubscriptionId",
        String(255),
        nullable=True,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        "planId",
        UUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="active",
        nullable=False,
    )  # active, past_due, canceled, trialing
    current_period_start: Mapped[Optional[datetime]] = mapped_column(
        "currentPeriodStart",
        DateTime(timezone=True),
        nullable=True,
    )
    current_period_end: Mapped[Optional[datetime]] = mapped_column(
        "currentPeriodEnd",
        DateTime(timezone=True),
        nullable=True,
    )

    workspace: Mapped["Workspace"] = relationship(
        "Workspace", back_populates="subscriptions", foreign_keys=[workspace_id]
    )
    plan: Mapped["Plan"] = relationship(
        "Plan", back_populates="subscriptions", foreign_keys=[plan_id]
    )
