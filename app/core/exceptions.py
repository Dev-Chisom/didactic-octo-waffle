"""Custom HTTP exceptions and error codes for upgrade flow and plan limits."""

from typing import Optional
from fastapi import HTTPException

FEATURE_LOCKED = "FEATURE_LOCKED"
PLAN_LIMIT_EXCEEDED = "PLAN_LIMIT_EXCEEDED"


def feature_locked_exception(
    required_plan: str,
    current_plan: str,
    message: Optional[str] = None,
) -> HTTPException:
    """Raise 403 with body for frontend 'Upgrade to unlock' modal."""
    return HTTPException(
        status_code=403,
        detail={
            "code": FEATURE_LOCKED,
            "requiredPlan": required_plan,
            "currentPlan": current_plan,
            "message": message or "This feature requires a higher plan.",
        },
    )


def plan_limit_exceeded_exception(
    required_plan: str,
    current_plan: str,
    limit_name: Optional[str] = None,
    message: Optional[str] = None,
) -> HTTPException:
    """Raise 422 with body for plan limit exceeded."""
    return HTTPException(
        status_code=422,
        detail={
            "code": PLAN_LIMIT_EXCEEDED,
            "requiredPlan": required_plan,
            "currentPlan": current_plan,
            "limitName": limit_name,
            "message": message or "Plan limit exceeded.",
        },
    )
