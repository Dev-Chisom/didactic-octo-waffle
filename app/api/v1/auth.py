"""Auth endpoints: register, login, refresh, me."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import CurrentUser, CurrentWorkspace, DbSession
from app.schemas.auth import (
    AuthResponse,
    ForgotPasswordRequest,
    GoogleCallbackRequest,
    LoginRequest,
    RegisterRequest,
    RefreshRequest,
    RefreshResponse,
    ResetPasswordRequest,
    TokenPair,
    UserResponse,
    WorkspaceResponse,
)
from app.services.auth_service import (
    register as do_register,
    login as do_login,
    refresh_tokens,
    request_password_reset,
    reset_password as do_reset_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse)
def register(
    body: RegisterRequest,
    db: DbSession,
):
    try:
        user, workspace, access, refresh = do_register(
            db, email=body.email, password=body.password, name=body.name
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return AuthResponse(
        user=UserResponse.model_validate(user),
        workspace=WorkspaceResponse(
            id=workspace.id,
            plan=workspace.plan,
            creditsBalance=workspace.credits_balance,
            limits=workspace.limits,
        ),
        tokens=TokenPair(accessToken=access, refreshToken=refresh),
    )


@router.post("/login", response_model=AuthResponse)
def login(
    body: LoginRequest,
    db: DbSession,
):
    try:
        user, workspace, access, refresh = do_login(db, email=body.email, password=body.password)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    return AuthResponse(
        user=UserResponse.model_validate(user),
        workspace=WorkspaceResponse(
            id=workspace.id,
            plan=workspace.plan,
            creditsBalance=workspace.credits_balance,
            limits=workspace.limits,
        ),
        tokens=TokenPair(accessToken=access, refreshToken=refresh),
    )


@router.post("/refresh", response_model=RefreshResponse)
def refresh(
    body: RefreshRequest,
    db: DbSession,
):
    try:
        _, access, refresh = refresh_tokens(db, body.refreshToken)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    return RefreshResponse(accessToken=access, refreshToken=refresh)


@router.post("/forgot-password")
def forgot_password(
    body: ForgotPasswordRequest,
    db: DbSession,
):
    """Request password reset email. Always returns 200 to avoid user enumeration."""
    request_password_reset(db, body.email)
    return {"ok": True}


@router.post("/reset-password")
def reset_password_route(
    body: ResetPasswordRequest,
    db: DbSession,
):
    """Set new password using reset token (single-use)."""
    try:
        do_reset_password(db, body.token, body.newPassword)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"ok": True}


@router.post("/google/callback", response_model=AuthResponse)
def google_callback(
    body: GoogleCallbackRequest,
    db: DbSession,
):
    """Exchange Google OAuth code for user/session. Body: { code }."""
    # TODO: exchange code for Google tokens, fetch profile, find or create user + workspace, return tokens
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Google OAuth callback not implemented; configure Google OAuth and exchange code for tokens",
    )
