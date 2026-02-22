"""Workspace and limits schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class CreditTransactionItem(BaseModel):
    """Single credit transaction for referral/credits history."""

    id: UUID
    type: str  # e.g. "referral", "usage", "purchase", "bonus", "refund"
    amount: int  # positive = credit, negative = usage
    reason: Optional[str] = None
    createdAt: datetime = Field(alias="created_at", serialization_alias="createdAt")

    model_config = {"from_attributes": True, "populate_by_name": True}


class WorkspaceLimitsResponse(BaseModel):
    plan: str
    limits: dict
    canUseAnimatedHook: bool = False
    maxSocialAccounts: int = 1
    maxPremiumEffectsPerVideo: int = 0
    maxSeries: int = 1
