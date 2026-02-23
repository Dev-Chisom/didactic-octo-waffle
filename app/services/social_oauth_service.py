"""Exchange OAuth codes for tokens and fetch basic profile per platform."""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.token_encryption import encrypt_token
from app.db.models.social_account import SocialAccount
from app.core.oauth_state import get_oauth_state, set_oauth_state


def _redirect_uri(base_url: str, platform: str) -> str:
    settings = get_settings()
    return f"{base_url.rstrip('/')}{settings.api_v1_prefix}/social/connect/{platform}/callback"


def store_state_and_return(
    state: str,
    workspace_id: UUID,
    platform: str,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    set_oauth_state(state, str(workspace_id), platform, extra=extra)


# --- TikTok ---
def _tiktok_exchange(
    code: str,
    redirect_uri: str,
    client_key: str,
    client_secret: str,
    code_verifier: Optional[str],
) -> dict[str, Any]:
    if not code_verifier:
        raise ValueError(
            "Missing PKCE code_verifier for TikTok OAuth. Please try connecting again."
        )
    resp = httpx.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        },
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json()
    err = data.get("error")
    if isinstance(err, dict) and err.get("code") and err.get("code") != "ok":
        raise ValueError(err.get("message") or f"TikTok token error: {err.get('code')}")
    if isinstance(err, str) and err:
        raise ValueError(data.get("message") or f"TikTok token error: {err}")
    return data


def _tiktok_user_info(access_token: str) -> dict[str, Any]:
    resp = httpx.get(
        "https://open.tiktokapis.com/v2/user/info/",
        headers={
            "Authorization": f"Bearer {access_token}",
        },
        params={"fields": "open_id,union_id,avatar_url,display_name"},
        timeout=10.0,
    )
    resp.raise_for_status()
    d = resp.json()
    err = d.get("error")
    if isinstance(err, dict) and err.get("code") and err.get("code") != "ok":
        raise ValueError(err.get("message") or f"TikTok user info error: {err.get('code')}")
    user = (d.get("data", {}).get("user") or {})
    return {
        "platform_user_id": user.get("open_id") or user.get("union_id") or "",
        "display_name": user.get("display_name") or "",
        "avatar_url": user.get("avatar_url") or None,
    }


# --- Instagram (Instagram API with Instagram Login) ---
def _instagram_exchange(
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str,
) -> dict[str, Any]:
    # Strip fragment if present (Instagram sometimes appends #_)
    code = code.split("#")[0].strip()
    resp = httpx.post(
        "https://api.instagram.com/oauth/access_token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": code,
        },
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


# --- YouTube (Google OAuth) ---
def _google_exchange(
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str,
) -> dict[str, Any]:
    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


def _youtube_channel(access_token: str) -> dict[str, Any]:
    resp = httpx.get(
        "https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10.0,
    )
    resp.raise_for_status()
    data = resp.json()
    items = data.get("items") or []
    if not items:
        return {"platform_user_id": "", "display_name": "YouTube", "avatar_url": None}
    sn = items[0].get("snippet", {})
    return {
        "platform_user_id": items[0].get("id", ""),
        "display_name": sn.get("title", "YouTube"),
        "avatar_url": (sn.get("thumbnails", {}).get("high", {}) or {}).get("url"),
    }


# --- Facebook ---
def _facebook_exchange(
    code: str,
    redirect_uri: str,
    app_id: str,
    app_secret: str,
) -> dict[str, Any]:
    resp = httpx.get(
        "https://graph.facebook.com/v21.0/oauth/access_token",
        params={
            "client_id": app_id,
            "client_secret": app_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        },
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()


def _facebook_me(access_token: str) -> dict[str, Any]:
    resp = httpx.get(
        "https://graph.facebook.com/v21.0/me",
        params={"fields": "id,name", "access_token": access_token},
        timeout=10.0,
    )
    resp.raise_for_status()
    d = resp.json()
    return {
        "platform_user_id": d.get("id", ""),
        "display_name": d.get("name", "Facebook"),
        "avatar_url": None,
    }


def _parse_expires_at(expires_in_seconds: Optional[int]) -> Optional[datetime]:
    if expires_in_seconds is None:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)


def handle_oauth_callback(
    db: Session,
    platform: str,
    state: str,
    code: Optional[str],
    base_url: str,
    error_from_platform: Optional[str] = None,
) -> tuple[Optional[SocialAccount], Optional[str]]:
    """
    Validate state, exchange code for tokens, create/update SocialAccount.
    Returns (account, None) on success or (None, error_message) on failure.
    """
    if error_from_platform or not code:
        return None, error_from_platform or "Missing authorization code"

    data = get_oauth_state(state)
    if not data:
        return None, "Invalid or expired state. Please try connecting again."
    workspace_id = data.get("workspace_id")
    if not workspace_id:
        return None, "Invalid state payload"
    code_verifier = data.get("code_verifier")

    settings = get_settings()
    platform = (platform or "").lower()
    redirect_uri = _redirect_uri(base_url, platform)

    try:
        if platform == "tiktok":
            if not settings.tiktok_client_key or not settings.tiktok_client_secret:
                return None, "TikTok OAuth not configured"
            token_data = _tiktok_exchange(
                code,
                redirect_uri,
                settings.tiktok_client_key,
                settings.tiktok_client_secret,
                code_verifier,
            )
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in")
            scope = token_data.get("scope", "")
            profile = _tiktok_user_info(access_token) if access_token else {}
            username = None
        elif platform == "instagram":
            if not settings.instagram_client_id or not settings.instagram_client_secret:
                return None, "Instagram OAuth not configured"
            token_data = _instagram_exchange(
                code, redirect_uri, settings.instagram_client_id, settings.instagram_client_secret
            )
            access_token = token_data.get("access_token")
            refresh_token = None
            expires_in = token_data.get("expires_in")
            scope = ""
            profile = {
                "platform_user_id": str(token_data.get("user_id", "")),
                "display_name": token_data.get("username", "Instagram"),
                "avatar_url": None,
            }
            username = token_data.get("username")
        elif platform == "youtube":
            if not settings.youtube_client_id or not settings.youtube_client_secret:
                return None, "YouTube OAuth not configured"
            token_data = _google_exchange(
                code, redirect_uri, settings.youtube_client_id, settings.youtube_client_secret
            )
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = token_data.get("expires_in")
            scope = token_data.get("scope", "")
            profile = _youtube_channel(access_token) if access_token else {}
            username = None
        elif platform == "facebook":
            if not settings.facebook_app_id or not settings.facebook_app_secret:
                return None, "Facebook OAuth not configured"
            token_data = _facebook_exchange(
                code, redirect_uri, settings.facebook_app_id, settings.facebook_app_secret
            )
            access_token = token_data.get("access_token")
            refresh_token = None
            expires_in = token_data.get("expires_in")
            scope = ""
            profile = _facebook_me(access_token) if access_token else {}
            username = None
        else:
            return None, f"Unknown platform: {platform}"
    except httpx.HTTPStatusError as e:
        body = e.response.text
        return None, f"Platform returned {e.response.status_code}: {body[:200]}"
    except Exception as e:
        return None, str(e)

    if not access_token:
        return None, "No access token in response"

    # Find existing account for this workspace + platform (by platform user id if we have it)
    workspace_uuid = UUID(workspace_id)
    existing = (
        db.query(SocialAccount)
        .filter(
            SocialAccount.workspace_id == workspace_uuid,
            SocialAccount.platform == platform,
        )
        .first()
    )
    if existing:
        # Update tokens and profile
        existing.access_token = encrypt_token(access_token)
        existing.refresh_token = encrypt_token(refresh_token) if refresh_token else existing.refresh_token
        existing.expires_at = _parse_expires_at(expires_in)
        existing.scopes = scope or existing.scopes
        existing.display_name = profile.get("display_name") or existing.display_name
        existing.username = username if username is not None else existing.username
        existing.avatar_url = profile.get("avatar_url") or existing.avatar_url
        existing.status = "connected"
        db.commit()
        db.refresh(existing)
        return existing, None

    account = SocialAccount(
        workspace_id=workspace_uuid,
        platform=platform,
        display_name=profile.get("display_name", platform.title()),
        username=username,
        avatar_url=profile.get("avatar_url"),
        status="connected",
        access_token=encrypt_token(access_token),
        refresh_token=encrypt_token(refresh_token) if refresh_token else None,
        scopes=scope,
        expires_at=_parse_expires_at(expires_in),
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account, None
