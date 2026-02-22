import secrets
from urllib.parse import urlencode, quote
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.config import get_settings
from app.dependencies import ConnectUserWorkspace, CurrentUser, CurrentWorkspace, DbSession
from app.db.models.social_account import SocialAccount
from app.schemas.social import (
    ConnectUrlResponse,
    SocialAccountResponse,
    SocialAccountUpdateRequest,
    SocialProviderResponse,
)
from app.services.social_oauth_service import store_state_and_return

router = APIRouter(prefix="/social", tags=["social"])


def _redirect_uri(request: Request, platform: str) -> str:
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/v1/social/connect/{platform}/callback"


def _build_connect_url(request: Request, platform: str, workspace_id: UUID) -> str:
    settings = get_settings()
    platform = (platform or "").lower()

    if platform == "tiktok":
        if not settings.tiktok_client_key:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="TikTok OAuth not configured. Set TIKTOK_CLIENT_KEY and TIKTOK_CLIENT_SECRET.",
            )
        redirect_uri = _redirect_uri(request, "tiktok")
        state = secrets.token_urlsafe(16)
        store_state_and_return(state, workspace_id, "tiktok")
        params = {
            "client_key": settings.tiktok_client_key,
            "scope": "user.info.basic,video.list,video.upload",
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": state,
        }
        return "https://www.tiktok.com/auth/authorize/?" + urlencode(params)

    if platform == "instagram":
        if not settings.instagram_client_id:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Instagram OAuth not configured. Set INSTAGRAM_CLIENT_ID and INSTAGRAM_CLIENT_SECRET.",
            )
        redirect_uri = _redirect_uri(request, "instagram")
        state = secrets.token_urlsafe(16)
        store_state_and_return(state, workspace_id, "instagram")
        params = {
            "client_id": settings.instagram_client_id,
            "redirect_uri": redirect_uri,
            "scope": "instagram_business_basic,instagram_business_content_publish",
            "response_type": "code",
            "state": state,
        }
        return "https://api.instagram.com/oauth/authorize?" + urlencode(params)

    if platform == "youtube":
        if not settings.youtube_client_id:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="YouTube OAuth not configured. Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET.",
            )
        redirect_uri = _redirect_uri(request, "youtube")
        state = secrets.token_urlsafe(16)
        store_state_and_return(state, workspace_id, "youtube")
        params = {
            "client_id": settings.youtube_client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join([
                "https://www.googleapis.com/auth/youtube.readonly",
                "https://www.googleapis.com/auth/youtube.upload",
                "https://www.googleapis.com/auth/userinfo.profile",
                "https://www.googleapis.com/auth/userinfo.email",
            ]),
            "response_type": "code",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)

    if platform == "facebook":
        if not settings.facebook_app_id:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Facebook OAuth not configured. Set FACEBOOK_APP_ID and FACEBOOK_APP_SECRET.",
            )
        redirect_uri = _redirect_uri(request, "facebook")
        state = secrets.token_urlsafe(16)
        store_state_and_return(state, workspace_id, "facebook")
        params = {
            "client_id": settings.facebook_app_id,
            "redirect_uri": redirect_uri,
            "scope": ",".join(["email", "public_profile", "pages_show_list", "pages_read_engagement", "pages_manage_posts"]),
            "response_type": "code",
            "state": state,
        }
        return "https://www.facebook.com/v21.0/dialog/oauth?" + urlencode(params)

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown platform: {platform}")


@router.get("/connect/{platform}")
def connect_start(platform: str, request: Request, user_workspace: ConnectUserWorkspace):
    _user, workspace = user_workspace
    auth_url = _build_connect_url(request, platform, workspace.id)
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/connect/{platform}/url", response_model=ConnectUrlResponse)
def connect_url(platform: str, request: Request, user: CurrentUser, workspace: CurrentWorkspace):
    auth_url = _build_connect_url(request, platform, workspace.id)
    return ConnectUrlResponse(url=auth_url)


@router.get("/providers", response_model=list[SocialProviderResponse])
def list_providers(user: CurrentUser, request: Request):
    base = str(request.base_url).rstrip("/")
    return [
        SocialProviderResponse(
            platform="tiktok",
            authUrl=f"{base}/api/v1/social/connect/tiktok",
            connectUrlPath="/api/v1/social/connect/tiktok/url",
            displayName="TikTok",
        ),
        SocialProviderResponse(
            platform="instagram",
            authUrl=f"{base}/api/v1/social/connect/instagram",
            connectUrlPath="/api/v1/social/connect/instagram/url",
            displayName="Instagram",
        ),
        SocialProviderResponse(
            platform="youtube",
            authUrl=f"{base}/api/v1/social/connect/youtube",
            connectUrlPath="/api/v1/social/connect/youtube/url",
            displayName="YouTube",
        ),
        SocialProviderResponse(
            platform="facebook",
            authUrl=f"{base}/api/v1/social/connect/facebook",
            connectUrlPath="/api/v1/social/connect/facebook/url",
            displayName="Facebook",
        ),
    ]


@router.get("/connect/{platform}/callback")
@router.post("/connect/{platform}/callback")
def connect_callback(platform: str, request: Request, db: DbSession):
    from app.services.social_oauth_service import handle_oauth_callback

    params = request.query_params
    state = params.get("state") or ""
    code = params.get("code")
    error = params.get("error") or params.get("error_description")
    base_url = str(request.base_url).rstrip("/")
    settings = get_settings()
    frontend = settings.frontend_url.rstrip("/")

    account, err = handle_oauth_callback(db, platform, state, code, base_url, error_from_platform=error)
    if err:
        return RedirectResponse(
            url=f"{frontend}/settings/accounts?error={quote(err)}",
            status_code=302,
        )
    return RedirectResponse(
        url=f"{frontend}/settings/accounts?connected=1&platform={platform}",
        status_code=302,
    )


@router.get("/accounts", response_model=list[SocialAccountResponse])
def list_accounts(
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    accounts = (
        db.query(SocialAccount)
        .filter(SocialAccount.workspace_id == workspace.id)
        .all()
    )
    return [SocialAccountResponse.model_validate(a) for a in accounts]


@router.patch("/accounts/{id}", response_model=SocialAccountResponse)
def update_account(
    id: UUID,
    body: SocialAccountUpdateRequest,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    acc = (
        db.query(SocialAccount)
        .filter(SocialAccount.id == id, SocialAccount.workspace_id == workspace.id)
        .first()
    )
    if not acc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    if body.displayName is not None:
        acc.display_name = body.displayName
    if body.status is not None:
        acc.status = body.status
    db.commit()
    db.refresh(acc)
    return SocialAccountResponse.model_validate(acc)


@router.delete("/accounts/{id}")
def disconnect_account(
    id: UUID,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    acc = (
        db.query(SocialAccount)
        .filter(SocialAccount.id == id, SocialAccount.workspace_id == workspace.id)
        .first()
    )
    if not acc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    db.delete(acc)
    db.commit()
    return {"ok": True}
