import uuid
import logging
from typing import Any, Dict, Optional

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.asset import Asset
from app.db.models.series import Series
from app.services.image_service import (
    DEFAULT_REPLICATE_SDXL_VERSION,
    _replicate_generate,
    _pexels_fetch,
)
from app.services.storage_service import upload_bytes
from app.services.generation_service import _reel_style_from_series, _topic_from_series


logger = logging.getLogger(__name__)


def _series_avatar_prompt(series: Series) -> str:
    """
    Build a single-character avatar prompt that matches the series style/topic.
    This is meant to create a reusable "hero" character for the series.
    """
    style = _reel_style_from_series(series)
    topic = _topic_from_series(series)
    prefs = series.script_preferences or {}
    tone = ""
    if isinstance(prefs, dict):
        tone = (prefs.get("tone") or "").strip()

    base = (
        f"Vertical 9:16 YouTube thumbnail style illustration of a single main character for a series about {topic}. "
        "Head-and-shoulders portrait, front facing, mouth clearly visible, expressive eyes, clean background. "
        "No text, no logos, no UI, no subtitles, no watermarks. High detail, crisp lines, vibrant but not neon colors."
    )

    if style == "cartoon":
        return (
            base
            + " Modern cartoon / comic style, smooth digital shading, outlined character, friendly but dramatic. "
            f"Overall tone: {tone or 'energetic, story-driven content'}."
        )
    if style == "anime":
        return (
            base
            + " Modern TV anime style, cel shading, big expressive eyes, dynamic hair. "
            f"Overall tone: {tone or 'emotional, character-driven adventure'}."
        )
    if style == "horror":
        return (
            base
            + " Dark cinematic horror comic style, moody lighting, subtle eerie atmosphere but PG-13 friendly. "
            "No gore, no explicit injury, no disturbing realism. "
            f"Overall tone: {tone or 'tense and suspenseful'}."
        )
    if style == "crime":
        return (
            base
            + " Semi-realistic graphic novel style, cinematic lighting, investigative / mystery vibe. "
            f"Overall tone: {tone or 'serious and intriguing'}."
        )
    # Faceless / fallback: still draw a character, but generic.
    return (
        base
        + " Semi-realistic digital illustration, neutral character suitable for a wide range of topics. "
        f"Overall tone: {tone or 'engaging educational content'}."
    )


def generate_avatar_image_bytes(series: Series) -> Optional[bytes]:
    """
    Generate a single avatar image for the series.

    Preference order:
    1. Replicate SDXL (primary, style-aware).
    2. Pexels fallback (if configured), using a portrait search query.

    Returns PNG bytes or None if both providers fail (with warnings logged).
    """
    settings = get_settings()

    prompt = _series_avatar_prompt(series)

    # 1) Replicate SDXL (primary)
    if settings.replicate_api_token:
        logger.info(
            "Generating avatar via Replicate SDXL for series_id=%s style=%s topic=%r",
            series.id,
            _reel_style_from_series(series),
            _topic_from_series(series),
        )
        with httpx.Client(timeout=120, trust_env=False) as client:
            img = _replicate_generate(
                client,
                token=settings.replicate_api_token,
                prompt=prompt,
                model_version=settings.replicate_model_version or DEFAULT_REPLICATE_SDXL_VERSION,
                width=720,
                height=1280,
                seed=42,
                steps=30,
                guidance_scale=7.5,
            )
            if img:
                return img
            logger.warning(
                "Replicate SDXL avatar generation returned no image for series_id=%s. "
                "Check earlier logs for HTTP/DNS errors.",
                series.id,
            )

    # 2) Pexels fallback (portrait image) if available
    if settings.pexels_api_key:
        logger.info(
            "Falling back to Pexels for avatar image for series_id=%s topic=%r",
            series.id,
            _topic_from_series(series),
        )
        query = _topic_from_series(series)
        with httpx.Client(timeout=60, trust_env=False) as client:
            img = _pexels_fetch(
                client,
                api_key=settings.pexels_api_key,
                query=query,
                width=720,
                height=1280,
            )
            if img:
                return img
            logger.warning(
                "Pexels avatar generation returned no image for series_id=%s query=%r.",
                series.id,
                query,
            )

    logger.warning(
        "Avatar image generation failed for series_id=%s: no providers succeeded. "
        "Check REPLICATE_API_TOKEN / PEXELS_API_KEY and network connectivity.",
        series.id,
    )
    return None


def ensure_series_avatar_image_url(db: Session, series: Series) -> str:
    """
    Ensure the series has an avatar image URL.

    - If script_preferences.avatar.imageUrl (or .url) is present, return it.
    - Otherwise, generate an avatar via SDXL, upload to S3, create an Asset,
      persist the URL into script_preferences, and return it.
    """
    prefs: Dict[str, Any] = series.script_preferences or {}
    if not isinstance(prefs, dict):
        prefs = {}
    avatar_cfg: Dict[str, Any] = prefs.get("avatar") or {}
    url = (avatar_cfg.get("imageUrl") or avatar_cfg.get("url") or "").strip()
    if url:
        return url

    img_bytes = generate_avatar_image_bytes(series)
    if not img_bytes:
        raise ValueError(
            "Failed to generate avatar image via Replicate. "
            "See avatar_service logs for details (network / DNS / Replicate errors)."
        )

    settings = get_settings()
    workspace_id = series.workspace_id
    key = f"workspaces/{workspace_id}/series/{series.id}/avatar.png"
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        url = upload_bytes(key, img_bytes, "image/png")
    else:
        url = f"https://storage.example.com/{key}"

    # Persist as an Asset for auditability / reuse.
    asset = Asset(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        type="image",
        source="generated",
        url=url,
        format="image/png",
        duration_seconds=None,
        metadata_={"series_id": str(series.id), "role": "series_avatar"},
    )
    db.add(asset)

    # Update series.script_preferences.avatar.imageUrl
    avatar_cfg = dict(avatar_cfg)
    avatar_cfg["imageUrl"] = url
    prefs["avatar"] = avatar_cfg
    series.script_preferences = prefs

    db.commit()
    db.refresh(series)
    return url

