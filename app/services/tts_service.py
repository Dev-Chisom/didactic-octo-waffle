"""TTS service using OpenAI TTS (and optional ElevenLabs)."""

from typing import Optional

from app.config import get_settings
from app.services.llm_service import get_openai_client

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


def synthesize(
    text: str,
    voice_id: str = "alloy",
    model: Optional[str] = None,
) -> bytes:
    """
    Synthesize speech from text using OpenAI TTS. Returns MP3 bytes.
    """
    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError("OpenAI API key not set; cannot use TTS")
    client = get_openai_client()
    model = model or settings.openai_tts_model
    resp = client.audio.speech.create(
        model=model,
        voice=voice_id,
        input=text[:4096],
    )
    return resp.content
