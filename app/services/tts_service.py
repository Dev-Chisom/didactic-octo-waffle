"""TTS service using OpenAI TTS or ElevenLabs, selectable via settings.

API keys (ELEVENLABS_API_KEY, etc.) must be set in env and never committed or shared.
"""

import logging
from typing import Any, Optional

import httpx

from app.config import Settings, get_settings
from app.services.llm_service import get_openai_client

logger = logging.getLogger(__name__)

# OpenAI TTS voice IDs and display info
OPENAI_VOICES = [
    {"id": "alloy", "name": "Alloy", "languageCode": "en-US", "gender": "neutral", "style": "neutral"},
    {"id": "echo", "name": "Echo", "languageCode": "en-US", "gender": "male", "style": "neutral"},
    {"id": "fable", "name": "Fable", "languageCode": "en-GB", "gender": "male", "style": "warm"},
    {"id": "onyx", "name": "Onyx", "languageCode": "en-US", "gender": "male", "style": "deep"},
    {"id": "nova", "name": "Nova", "languageCode": "en-US", "gender": "female", "style": "friendly"},
    {"id": "shimmer", "name": "Shimmer", "languageCode": "en-US", "gender": "female", "style": "warm"},
]


def list_voices(language_code: Optional[str] = None) -> list[dict]:
    """Return available TTS voices (OpenAI). Optionally filter by language."""
    settings = get_settings()
    if not settings.openai_api_key:
        return []
    voices = list(OPENAI_VOICES)
    if language_code:
        voices = [v for v in voices if v["languageCode"] == language_code]
    return voices


def get_elevenlabs_model_id_for_request(
    text: str,
    emotion_tag: Optional[str],
    settings: Settings,
) -> str:
    """
    Cost-effective model choice: v3 for short emotional dialogue, else configured model (turbo/flash).
    Used by _synthesize_elevenlabs; exposed for unit tests.
    """
    if emotion_tag and emotion_tag.strip() and len(text.strip()) <= 500:
        return "eleven_v3"
    return (settings.elevenlabs_model_id or "").strip() or "eleven_multilingual_v2"


def _synthesize_openai(
    text: str,
    voice_id: str,
    model: Optional[str],
    settings: Settings,
) -> bytes:
    if not settings.openai_api_key:
        raise ValueError("OpenAI API key not set; cannot use OpenAI TTS")
    client = get_openai_client()
    model = model or settings.openai_tts_model
    resp = client.audio.speech.create(
        model=model,
        voice=voice_id,
        input=text[:4096],
    )
    return resp.content


def _synthesize_elevenlabs(
    text: str,
    voice_id: str,
    settings: Settings,
    *,
    emotion_tag: Optional[str] = None,
    stability: Optional[float] = None,
    similarity_boost: Optional[float] = None,
) -> bytes:
    # Strip to avoid 401 from accidental spaces when pasting into .env
    api_key = (settings.elevenlabs_api_key or "").strip()
    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY not set; cannot use ElevenLabs TTS")

    model_id = get_elevenlabs_model_id_for_request(text, emotion_tag, settings)

    # Resolve the ElevenLabs voice_id for the URL: /v1/text-to-speech/{voice_id}
    # If caller passed an OpenAI name (e.g. "alloy") or empty, use ELEVENLABS_VOICE_ID.
    openai_voice_ids = {v["id"] for v in OPENAI_VOICES}
    if not voice_id or (voice_id.strip() in openai_voice_ids):
        elevenlabs_voice_id = (settings.elevenlabs_voice_id or "").strip()
    else:
        elevenlabs_voice_id = voice_id.strip()
    if not elevenlabs_voice_id:
        raise ValueError(
            "No valid ElevenLabs voice ID. Set ELEVENLABS_VOICE_ID or pass an ElevenLabs voice_id (not an OpenAI name like 'alloy')."
        )

    # Per ElevenLabs docs: v3=5k, multilingual_v2=10k, flash/turbo v2=30k, flash/turbo v2.5=40k
    max_chars = 5_000
    if "flash_v2_5" in model_id or "turbo_v2_5" in model_id:
        max_chars = 40_000
    elif "flash_v2" in model_id or "turbo_v2" in model_id:
        max_chars = 30_000
    elif "multilingual_v2" in model_id:
        max_chars = 10_000
    payload_text = text[:max_chars]
    # Eleven v3 (and some others) support audio tags for emotion: [sad], [whispers], [laughs], etc.
    if emotion_tag and emotion_tag.strip():
        tag = emotion_tag.strip()
        if not tag.startswith("["):
            tag = f"[{tag}]"
        if not tag.endswith("]"):
            tag = f"{tag}]" if tag.startswith("[") else f"[{tag}]"
        payload_text = f"{tag} {payload_text}"

    # Non-streaming: we need full audio bytes for WAV conversion and S3 upload. For lower latency, /stream is available.
    base = (settings.elevenlabs_base_url or "https://api.elevenlabs.io/v1").rstrip("/")
    url = f"{base}/text-to-speech/{elevenlabs_voice_id}"
    headers = {
        "xi-api-key": api_key,
        "accept": "audio/mpeg",
        "Content-Type": "application/json",
    }
    stab = stability if stability is not None else 0.5
    sim = similarity_boost if similarity_boost is not None else 0.75
    payload: dict[str, Any] = {
        "text": payload_text,
        "model_id": model_id,
        "voice_settings": {"stability": stab, "similarity_boost": sim},
    }

    # trust_env=False avoids broken proxy env vars affecting Celery workers.
    transport = httpx.HTTPTransport(retries=3)
    with httpx.Client(timeout=60.0, trust_env=False, transport=transport) as client:
        try:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.content
        except httpx.RequestError as e:
            logger.warning("ElevenLabs request failed: url=%s error=%s", url, e)
            raise


def synthesize(
    text: str,
    voice_id: str = "alloy",
    model: Optional[str] = None,
    *,
    emotion_tag: Optional[str] = None,
    stability: Optional[float] = None,
) -> bytes:
    """
    Synthesize speech from text. Returns MP3 bytes.

    Provider is selected via Settings.tts_provider:
    - "openai" (default): OpenAI TTS
    - "elevenlabs": ElevenLabs TTS (falls back to OpenAI if ElevenLabs is unreachable)

    Optional (ElevenLabs): emotion_tag (e.g. "whispers", "[sad]") for Eleven v3 audio tags;
    stability (0-1, lower=more expressive). Narrator vs character: use different voice_id per call.
    """
    settings = get_settings()
    provider = getattr(settings, "tts_provider", "openai")
    if provider == "elevenlabs":
        try:
            return _synthesize_elevenlabs(
                text,
                voice_id=voice_id,
                settings=settings,
                emotion_tag=emotion_tag,
                stability=stability,
            )
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            status = getattr(e, "response", None)
            status_code = status.status_code if status is not None else None
            logger.warning(
                "ElevenLabs TTS failed (%s%s); falling back to OpenAI TTS so the reel can complete.",
                f"HTTP {status_code} " if status_code else "",
                e,
            )
            if status_code == 401:
                logger.info(
                    "ElevenLabs 401: check ELEVENLABS_API_KEY at https://elevenlabs.io/app/settings/api-keys "
                    "(no spaces, use current key after any regeneration)."
                )
            # Use OpenAI voice_id (alloy, nova, etc.); series typically sends these.
            openai_voice = voice_id if voice_id in {v["id"] for v in OPENAI_VOICES} else "alloy"
            return _synthesize_openai(text, voice_id=openai_voice, model=model, settings=settings)
    return _synthesize_openai(text, voice_id=voice_id, model=model, settings=settings)
