"""Plan model for subscription tiers."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import Float, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.subscription import Subscription


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # free, pro, agency
    monthly_price: Mapped[float] = mapped_column("monthlyPrice", Float, default=0)
    annual_price: Mapped[float] = mapped_column("annualPrice", Float, default=0)
    limits: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    # e.g. maxEffects, maxSeries, premiumFlags, maxSocialAccounts, etc.

    subscriptions: Mapped[List["Subscription"]] = relationship(
        "Subscription", back_populates="plan"
    )
