"""API v1 router: include all route modules, GET /me, PATCH /me."""

from fastapi import APIRouter

from app.api.v1 import (
    auth,
    series,
    episodes,
    workspaces,
    voices,
    music,
    social,
    analytics,
    assets,
    scheduled_posts,
)
from app.dependencies import CurrentUser, CurrentWorkspace, DbSession
from app.schemas.auth import UserResponse, WorkspaceResponse
from app.schemas.settings import MeUpdateRequest

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(series.router)
api_router.include_router(episodes.router)
api_router.include_router(workspaces.router)
api_router.include_router(voices.router)
api_router.include_router(music.router)
api_router.include_router(social.router)
api_router.include_router(analytics.router)
api_router.include_router(assets.router)
api_router.include_router(scheduled_posts.router)


@api_router.get("/me")
def me(user: CurrentUser, workspace: CurrentWorkspace):
    """Return current user + workspace context + permissions."""
    return {
        "user": UserResponse.model_validate(user),
        "workspace": WorkspaceResponse(
            id=workspace.id,
            plan=workspace.plan,
            creditsBalance=workspace.credits_balance,
            limits=workspace.limits,
        ),
    }


@api_router.patch("/me", response_model=dict)
def update_me(
    body: MeUpdateRequest,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    """Update current user profile (e.g. name)."""
    if body.name is not None:
        user.name = body.name
        db.commit()
        db.refresh(user)
    return {"user": UserResponse.model_validate(user)}
