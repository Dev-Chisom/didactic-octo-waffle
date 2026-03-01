"""Auth endpoints: register, login, refresh, me, Google OAuth."""

import secrets
from typing import Optional
from urllib.parse import urlencode, quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.config import get_settings
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
    login_or_register_with_google,
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


GOOGLE_OAUTH_SCOPES = "openid email profile"


@router.get("/google")
def google_oauth_start():
    """Redirect to Google OAuth consent screen. Requires GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."""
    settings = get_settings()
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth not configured (missing GOOGLE_CLIENT_ID)",
        )
    base_url = (settings.public_base_url or "").rstrip("/") or "http://localhost:8000"
    redirect_uri = f"{base_url}{settings.api_v1_prefix}/auth/google/callback"
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_OAUTH_SCOPES,
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    response = RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="oauth_state",
        value=state,
        max_age=600,
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/google/callback")
def google_oauth_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    db: DbSession = None,
):
    """Handle Google OAuth redirect: exchange code for tokens, create/find user, redirect to frontend with tokens."""
    settings = get_settings()
    frontend_url = (settings.frontend_url or "").rstrip("/") or "http://localhost:3000"
    if error:
        msg = error_description or error
        return RedirectResponse(
            url=f"{frontend_url}/auth/callback?error={quote(msg)}",
            status_code=status.HTTP_302_FOUND,
        )
    if not code:
        # Often means redirect_uri mismatch in Google Console, or request came without going through Google
        detail = (
            "Missing code from Google. Check: 1) PUBLIC_BASE_URL matches this server (e.g. ngrok URL). "
            "2) In Google Cloud Console, add this exact redirect URI: "
            f"{(settings.public_base_url or 'http://localhost:8000').rstrip('/')}{settings.api_v1_prefix}/auth/google/callback"
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth not configured",
        )
    base_url = (settings.public_base_url or "").rstrip("/") or "http://localhost:8000"
    redirect_uri = f"{base_url}{settings.api_v1_prefix}/auth/google/callback"
    try:
        user, workspace, access, refresh = login_or_register_with_google(
            db, code=code, redirect_uri=redirect_uri
        )
    except ValueError as e:
        return RedirectResponse(
            url=f"{frontend_url}/auth/callback?error={quote(str(e))}",
        status_code=status.HTTP_302_FOUND,
    )
    fragment = f"access_token={access}&refresh_token={refresh}&token_type=bearer"
    return RedirectResponse(
        url=f"{frontend_url}/auth/callback#{fragment}",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/google/callback", response_model=AuthResponse)
def google_callback_post(
    body: GoogleCallbackRequest,
    db: DbSession,
):
    """Exchange Google OAuth code for user/session. Body: { code }. Alternative to GET callback when frontend receives the code."""
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth not configured",
        )
    base_url = (settings.public_base_url or "").rstrip("/") or "http://localhost:8000"
    redirect_uri = f"{base_url}{settings.api_v1_prefix}/auth/google/callback"
    try:
        user, workspace, access, refresh = login_or_register_with_google(
            db, code=body.code, redirect_uri=redirect_uri
        )
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
