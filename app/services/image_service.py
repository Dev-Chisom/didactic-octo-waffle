"""Image generation via Replicate (primary) and Pexels (fallback)."""

from __future__ import annotations

import io
import re
import time
import logging
from typing import Optional

import httpx
from PIL import Image

from app.config import get_settings

logger = logging.getLogger(__name__)

# Default SDXL model version (stability-ai/sdxl) - same as reel_engine
DEFAULT_REPLICATE_SDXL_VERSION = "a00d0b7dcbb9c3fbb34ba87d2d5b46c56969c84a628bf778a7fdaec30b1b99c5"

_SCENE_STYLE_SUFFIX = (
    " Cinematic dramatic lighting, photorealistic, film grain, shallow depth of field, "
    "professional color grading, no text or logos, vertical composition 9:16, hyper realistic. "
    "Family‑friendly, PG‑13 only, no gore, no graphic violence, no weapons, no nudity. "
    "Absolutely no letters, words, subtitles, captions, signage, watermarks, UI, or symbols."
)

_NEGATIVE_PROMPT = (
    "text, watermark, logo, subtitles, lowres, blurry, deformed hands, extra fingers, "
    "distorted face, bad anatomy, cartoon, anime"
)


def _prompt_from_script(script_text: str, max_chars: int = 800) -> str:
    text = (script_text or "").strip()
    if not text:
        return (
            "Photorealistic cinematic scene: soft gradient sky and distant mountains, "
            "professional color grading, shallow depth of field, vertical composition, no text."
        )
    snippet = text[:max_chars].strip()
    if len(text) > max_chars:
        snippet += "..."
    return (
        "Photorealistic, cinematic photograph suitable as the background for a short vertical video. "
        f"Theme or mood of the video: {snippet}. "
        "Style: realistic photography, film look, professional color grading, shallow depth of field, "
        "high quality, no text or logos, no cartoon or illustration. Portrait orientation, 9:16 aspect. "
        "Family‑friendly, PG‑13 tone, no gore, no graphic violence, no explicit injuries or disturbing content."
    )


def _scene_prompt(visual_description: str, max_chars: int = 400) -> str:
    desc = (visual_description or "").strip()[:max_chars]
    if not desc:
        desc = "atmospheric cinematic moment, moody lighting"
    return (
        "Create an image with zero readable text. Do not include any writing of any kind. "
        + desc
        + _SCENE_STYLE_SUFFIX
    )


def _search_query_from_description(visual_description: str, max_words: int = 5) -> str:
    """Extract a short Pexels-friendly search query from visual description."""
    text = (visual_description or "").strip()
    if not text:
        return "cinematic atmosphere moody lighting"
    words = re.findall(r"[A-Za-z']+", text)
    meaningful = [w for w in words if w.lower() not in {"the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or", "with", "no", "not"}]
    return " ".join(meaningful[:max_words]) if meaningful else text[:50]


def _replicate_generate(
    client: httpx.Client,
    *,
    token: str,
    prompt: str,
    negative_prompt: str = _NEGATIVE_PROMPT,
    width: int = 720,
    height: int = 1280,
    model_version: str = DEFAULT_REPLICATE_SDXL_VERSION,
    seed: int = 42,
    steps: int = 28,
    guidance_scale: float = 7.5,
) -> Optional[bytes]:
    """Create Replicate prediction, poll until done, return image bytes."""
    headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}
    payload = {
        "version": model_version,
        "input": {
            "prompt": prompt[:4000],
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "num_inference_steps": steps,
            "guidance_scale": guidance_scale,
            "seed": seed,
            "disable_safety_checker": True,
        },
    }
    r = client.post("https://api.replicate.com/v1/predictions", headers=headers, json=payload)
    if r.status_code >= 400:
        logger.warning("Replicate create failed: %s %s", r.status_code, r.text[:200])
        return None
    data = r.json()
    pred_id = data.get("id")
    if not pred_id:
        return None

    for _ in range(120):
        time.sleep(1.5)
        r = client.get(f"https://api.replicate.com/v1/predictions/{pred_id}", headers=headers)
        if r.status_code != 200:
            continue
        data = r.json()
        status = str(data.get("status") or "")
        if status == "failed":
            logger.warning("Replicate prediction failed: %s", data.get("error", data))
            return None
        if status != "succeeded":
            continue
        output = data.get("output")
        url = None
        if isinstance(output, str):
            url = output
        elif isinstance(output, list) and output and isinstance(output[0], str):
            url = output[0]
        if url and url.startswith(("http://", "https://")):
            start = time.monotonic()
            try:
                img_r = client.get(url, follow_redirects=True, timeout=60.0)
                elapsed = time.monotonic() - start
                if img_r.status_code == 200:
                    logger.info(
                        "Replicate image download succeeded: url=%s status=%s elapsed=%.2fs bytes=%d",
                        url,
                        img_r.status_code,
                        elapsed,
                        len(img_r.content or b""),
                    )
                    return img_r.content
                logger.warning(
                    "Replicate image download non-200: url=%s status=%s elapsed=%.2fs",
                    url,
                    img_r.status_code,
                    elapsed,
                )
            except httpx.RequestError as e:
                elapsed = time.monotonic() - start
                logger.warning(
                    "Replicate image download failed (DNS/network): %s url=%s elapsed=%.2fs. "
                    "URL host may be unreachable; check VPN/DNS.",
                    e,
                    url,
                    elapsed,
                )
                return None
        return None
    logger.warning("Replicate prediction timed out")
    return None


def _pexels_fetch(
    client: httpx.Client,
    *,
    api_key: str,
    query: str,
    width: int = 720,
    height: int = 1280,
) -> Optional[bytes]:
    """Fetch portrait image from Pexels, resize to target dimensions, return PNG bytes."""
    try:
        headers = {"Authorization": api_key}
        params = {"query": query[:100], "per_page": 1, "orientation": "portrait", "size": "large"}
        r = client.get("https://api.pexels.com/v1/search", headers=headers, params=params)
        if r.status_code != 200:
            logger.warning("Pexels search failed: %s", r.status_code)
            return None
        data = r.json()
        photos = data.get("photos") or []
        if not photos:
            logger.warning("Pexels returned no results for query: %r", query)
            return None
        src = photos[0].get("src") or {}
        url = src.get("large2x") or src.get("large") or src.get("original")
        if not url:
            return None
        img_r = client.get(url)
        if img_r.status_code != 200:
            return None
        img_bytes = img_r.content
    except httpx.ConnectError as e:
        logger.warning("Pexels request failed (DNS/network): %s", e)
        return None
    try:
        im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        target_ar = width / float(height)
        w0, h0 = im.size
        cur_ar = w0 / float(h0)
        if cur_ar > target_ar:
            new_w = int(round(h0 * target_ar))
            left = (w0 - new_w) // 2
            im = im.crop((left, 0, left + new_w, h0))
        else:
            new_h = int(round(w0 / target_ar))
            top = (h0 - new_h) // 2
            im = im.crop((0, top, w0, top + new_h))
        im = im.resize((width, height), resample=Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    except Exception as e:
        logger.warning("Pexels image resize failed: %s", e)
        return None


def generate_video_image(script_text: Optional[str] = None) -> Optional[bytes]:
    """Generate a single cover image for a video. Replicate primary, Pexels fallback."""
    settings = get_settings()
    prompt = _prompt_from_script(script_text or "")
    search_query = _search_query_from_description(script_text or "cinematic mood atmosphere")
    width = 720
    height = 1280

    with httpx.Client(timeout=120, trust_env=False) as client:
        if settings.replicate_api_token:
            img = _replicate_generate(
                client,
                token=settings.replicate_api_token,
                prompt=prompt,
                model_version=settings.replicate_model_version or DEFAULT_REPLICATE_SDXL_VERSION,
                width=width,
                height=height,
            )
            if img:
                return img
        if settings.pexels_api_key:
            return _pexels_fetch(
                client,
                api_key=settings.pexels_api_key,
                query=search_query,
                width=width,
                height=height,
            )
    return None


def generate_scene_image(visual_description: str, scene_index: int = 0) -> Optional[bytes]:
    """Generate a scene image. Replicate primary, Pexels fallback."""
    settings = get_settings()
    prompt = _scene_prompt(visual_description)
    search_query = _search_query_from_description(visual_description)
    width = 720
    height = 1280
    seed = 42 + scene_index

    with httpx.Client(timeout=120, trust_env=False) as client:
        if settings.replicate_api_token:
            img = _replicate_generate(
                client,
                token=settings.replicate_api_token,
                prompt=prompt,
                model_version=settings.replicate_model_version or DEFAULT_REPLICATE_SDXL_VERSION,
                width=width,
                height=height,
                seed=seed,
            )
            if img:
                return img
        if settings.pexels_api_key:
            img = _pexels_fetch(
                client,
                api_key=settings.pexels_api_key,
                query=search_query,
                width=width,
                height=height,
            )
            if img:
                return img
    return None


def generate_all_scene_images(visual_descriptions: list[str]) -> list[Optional[bytes]]:
    """Generate images for each scene description."""
    return [generate_scene_image(desc, scene_index=i) for i, desc in enumerate(visual_descriptions)]
