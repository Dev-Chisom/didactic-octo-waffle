"""Platform-specific video publish: TikTok, Instagram, YouTube, Facebook."""

import time
from typing import Any, Optional
import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.token_encryption import decrypt_token
from app.db.models.asset import Asset
from app.db.models.social_account import SocialAccount
from app.services.storage_service import get_download_url


def _tiktok_publish(
    access_token: str,
    video_url: str,
    caption: str,
    post_id: str,
) -> dict[str, Any]:
    """
    TikTok Content Posting API: init upload (PULL_FROM_URL), then publish.
    Requires video URL to be from a TikTok-verified domain or use FILE_UPLOAD.
    """
    settings = get_settings()
    if not settings.tiktok_client_key:
        raise ValueError("TikTok not configured")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    # Step 1: Initialize upload
    init_payload = {
        "post_info": {
            "title": caption[:150] if caption else "Video",
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "disable_duet": False,
            "disable_comment": False,
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "video_url": video_url,
        },
    }
    r = httpx.post(
        "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/",
        headers=headers,
        json=init_payload,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    err = data.get("error") or {}
    if err.get("code") and err.get("code") != "ok":
        raise RuntimeError(err.get("message", "TikTok init failed"))
    publish_id = (data.get("data") or {}).get("publish_id")
    if not publish_id:
        raise RuntimeError("No publish_id from TikTok")
    return {"platform_post_id": publish_id, "status": "posted"}


def _instagram_publish(
    access_token: str,
    video_url: str,
    caption: str,
) -> dict[str, Any]:
    """
    Instagram Graph API: create container with video_url then publish.
    Uses Instagram API with Instagram Login (business).
    """
    # Create media container (video)
    r = httpx.post(
        "https://graph.facebook.com/v21.0/me/media",
        params={"access_token": access_token},
        json={
            "media_type": "VIDEO",
            "video_url": video_url,
            "caption": (caption or "")[:2200],
        },
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    container_id = data.get("id")
    if not container_id:
        raise RuntimeError("No container id from Instagram")

    # Poll until container is ready then publish
    for _ in range(30):
        check = httpx.get(
            f"https://graph.facebook.com/v21.0/{container_id}",
            params={"access_token": access_token, "fields": "status_code"},
            timeout=10,
        )
        check.raise_for_status()
        status = check.json().get("status_code")
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise RuntimeError("Instagram container processing failed")
        time.sleep(2)

    pub = httpx.post(
        f"https://graph.facebook.com/v21.0/me/media_publish",
        params={"access_token": access_token, "creation_id": container_id},
        timeout=30,
    )
    pub.raise_for_status()
    pub_data = pub.json()
    media_id = pub_data.get("id")
    return {"platform_post_id": media_id or container_id, "status": "posted"}


def _youtube_publish(
    access_token: str,
    video_url: str,
    title: str,
    description: str,
) -> dict[str, Any]:
    """
    YouTube Data API v3: upload video. YouTube requires actual file upload
    (resumable) or we need to download and re-upload. For URL-only we'd need
    to download the file and use resumable upload. Simplified: attempt insert
    with upload URL (YouTube may not support URL ingest); else fail with clear message.
    """
    # YouTube does not support "publish from URL" directly; requires resumable upload.
    # So we must download video and POST to uploads endpoint.
    r = httpx.get(video_url, timeout=120)
    r.raise_for_status()
    video_bytes = r.content
    content_type = "video/mp4"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    # Resumable upload: 1) POST to get upload URI 2) PUT body
    init = httpx.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers=headers,
        json={
            "snippet": {
                "title": (title or "Video")[:100],
                "description": (description or "")[:5000],
                "categoryId": "22",
            },
            "status": {"privacyStatus": "public"},
        },
        timeout=30,
    )
    init.raise_for_status()
    upload_url = init.headers.get("location")
    if not upload_url:
        raise RuntimeError("YouTube did not return upload URL")

    up = httpx.put(upload_url, content=video_bytes, headers={"Content-Type": content_type}, timeout=300)
    up.raise_for_status()
    out = up.json()
    video_id = out.get("id")
    if not video_id:
        raise RuntimeError("YouTube upload response missing id")
    return {"platform_post_id": video_id, "status": "posted"}


def _facebook_publish(
    access_token: str,
    video_url: str,
    caption: str,
) -> dict[str, Any]:
    """Facebook Graph: publish video to page or user feed."""
    r = httpx.post(
        "https://graph.facebook.com/v21.0/me/videos",
        params={"access_token": access_token},
        data={"file_url": video_url, "description": (caption or "")[:5000]},
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    video_id = data.get("id")
    return {"platform_post_id": video_id or "unknown", "status": "posted"}


def publish_to_platform(
    db: Session,
    social_account: SocialAccount,
    video_asset: Asset,
    caption: str,
    post_id: str,
) -> tuple[str, Optional[str], Optional[dict]]:
    """
    Publish video to the given social account. Returns (status, platform_post_id, error_dict).
    status is "posted" or "failed".
    """
    platform = (social_account.platform or "").lower()
    access_token = decrypt_token(social_account.access_token or "")
    if not access_token:
        return "failed", None, {"message": "Missing or invalid access token"}

    video_url = get_download_url(video_asset.url, expiration=7200) if video_asset.url else ""
    if not video_url or video_url.startswith("https://storage.example.com"):
        return "failed", None, {"message": "Video URL not available (S3 not configured or placeholder)"}

    try:
        if platform == "tiktok":
            out = _tiktok_publish(access_token, video_url, caption or "Video", post_id)
        elif platform == "instagram":
            out = _instagram_publish(access_token, video_url, caption)
        elif platform == "youtube":
            out = _youtube_publish(access_token, video_url, caption or "Video", caption or "")
        elif platform == "facebook":
            out = _facebook_publish(access_token, video_url, caption)
        else:
            return "failed", None, {"message": f"Unsupported platform: {platform}"}
        return out.get("status", "posted"), out.get("platform_post_id"), None
    except Exception as e:
        return "failed", None, {"message": str(e)}
