from __future__ import annotations

import base64
import logging
from typing import List, Optional

from app.config import get_settings
from app.services.llm_service import get_openai_client

logger = logging.getLogger(__name__)

_SCENE_STYLE_SUFFIX = (
    " Cinematic dramatic lighting, photorealistic, film grain, shallow depth of field, "
    "professional color grading, no text or logos, vertical composition 9:16, hyper realistic. "
    "Family‑friendly, PG‑13 only, no gore, no graphic violence, no weapons, no nudity. "
    "Absolutely no letters, words, subtitles, captions, signage, watermarks, UI, or symbols."
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


def generate_video_image(script_text: Optional[str] = None) -> Optional[bytes]:
    settings = get_settings()
    if not settings.openai_api_key or not settings.openai_generate_video_image:
        return None
    model = settings.openai_image_model or "dall-e-3"
    prompt = _prompt_from_script(script_text or "")
    try:
        client = get_openai_client()
        kwargs = {
            "model": model,
            "prompt": prompt[:4000],
            "size": "1024x1792",
            "n": 1,
            "response_format": "b64_json",
            "quality": "standard",
        }
        if model == "dall-e-3":
            kwargs["style"] = "natural"
        resp = client.images.generate(**kwargs)
        if not resp.data or len(resp.data) == 0:
            logger.warning("OpenAI image generation returned no data")
            return None
        b64 = resp.data[0].b64_json
        if not b64:
            return None
        return base64.b64decode(b64)
    except Exception as e:
        logger.warning("OpenAI image generation failed: %s", e)
        return None


def generate_scene_image(visual_description: str, scene_index: int = 0) -> Optional[bytes]:
    settings = get_settings()
    if not settings.openai_api_key or not settings.openai_generate_video_image:
        return None
    model = settings.openai_image_model or "dall-e-3"
    prompt = _scene_prompt(visual_description)

    def _generate(prompt_text: str) -> Optional[bytes]:
        client = get_openai_client()
        kwargs = {
            "model": model,
            "prompt": prompt_text[:4000],
            "size": "1024x1792",
            "n": 1,
            "response_format": "b64_json",
            "quality": "standard",
        }
        if model == "dall-e-3":
            kwargs["style"] = "natural"
        resp = client.images.generate(**kwargs)
        if not resp.data or len(resp.data) == 0:
            logger.warning("OpenAI scene image %s returned no data", scene_index)
            return None
        b64 = resp.data[0].b64_json
        if not b64:
            return None
        return base64.b64decode(b64)

    try:
        first = _generate(prompt)
        if first is not None:
            return first
    except Exception as e:
        msg = str(e)
        logger.warning("OpenAI scene image %s failed: %s", scene_index, e)
        # If this looks like a safety / content policy block, fall back to a very safe, abstract prompt.
        if "content_policy_violation" not in msg and "safety system" not in msg:
            return None

    # Fallback: gentle abstract background so we never show a harsh black frame.
    try:
        safe_prompt = (
            "Soft, abstract atmospheric background with gentle gradients and subtle light rays, "
            "no characters, no creatures, no text, no symbols, no violence, suitable for a "
            "family‑friendly short vertical horror story. Vertical 9:16 composition, cinematic lighting."
        )
        return _generate(safe_prompt)
    except Exception as e2:
        logger.warning("OpenAI fallback scene image %s also failed: %s", scene_index, e2)
        return None


def generate_all_scene_images(visual_descriptions: List[str]) -> List[Optional[bytes]]:
    out: List[Optional[bytes]] = []
    for i, desc in enumerate(visual_descriptions):
        out.append(generate_scene_image(desc, scene_index=i))
    return out
