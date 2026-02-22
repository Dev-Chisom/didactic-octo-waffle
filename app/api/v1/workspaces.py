"""Workspace limits, settings, and credit history."""

from uuid import UUID
from typing import Optional
from fastapi import APIRouter, Query, HTTPException, status

from app.dependencies import CurrentUser, CurrentWorkspace, DbSession
from app.db.models.credit_transaction import CreditTransaction
from app.schemas.workspace import CreditTransactionItem, WorkspaceLimitsResponse
from app.services.credits_service import get_workspace_limits

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


# Declare credit-transactions before limits so the literal path is matched first
@router.get("/{id}/credit-transactions", response_model=list[CreditTransactionItem])
def list_credit_transactions(
    id: UUID,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
    limit: int = Query(50, le=100),
):
    """List credit transactions for the workspace (referral & credits history)."""
    if workspace.id != id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace access denied")
    rows = (
        db.query(CreditTransaction)
        .filter(CreditTransaction.workspace_id == id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(limit)
        .all()
    )
    return [CreditTransactionItem.model_validate(r) for r in rows]


@router.get("/{id}/limits", response_model=WorkspaceLimitsResponse)
def get_limits(
    id: UUID,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    if workspace.id != id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workspace access denied")
    return WorkspaceLimitsResponse(**get_workspace_limits(workspace))
