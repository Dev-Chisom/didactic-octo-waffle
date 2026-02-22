"""Voice and TTS preview endpoints."""

from typing import Optional
from fastapi import APIRouter, Query, HTTPException, status

from app.dependencies import CurrentUser, CurrentWorkspace
from app.schemas.voice_music import (
    VoiceItem,
    VoicePreviewRequest,
    VoicePreviewResponse,
)
from app.services.tts_service import list_voices as tts_list_voices, synthesize as tts_synthesize
from app.services.storage_service import upload_bytes, voice_preview_key, presigned_url
from app.config import get_settings

router = APIRouter(prefix="/voices", tags=["voices"])


@router.get("", response_model=list[VoiceItem])
def list_voices(
    user: CurrentUser,
    workspace: CurrentWorkspace,
    languageCode: Optional[str] = Query(None),
):
    """Return available voices from TTS provider (OpenAI), optionally filtered by language."""
    raw = tts_list_voices(languageCode)
    if not raw:
        # Fallback placeholder when TTS not configured
        return [
            VoiceItem(
                id="en-US-1",
                name="English (US) - Standard",
                languageCode="en-US",
                gender="female",
                style="calm",
                isPremium=False,
                previewUrl=None,
            ),
            VoiceItem(
                id="en-US-2",
                name="English (US) - Energetic",
                languageCode="en-US",
                gender="male",
                style="energetic",
                isPremium=False,
                previewUrl=None,
            ),
        ]
    return [
        VoiceItem(
            id=v["id"],
            name=v["name"],
            languageCode=v["languageCode"],
            gender=v["gender"],
            style=v["style"],
            isPremium=False,
            previewUrl=None,
        )
        for v in raw
    ]


@router.post("/preview", response_model=VoicePreviewResponse)
def preview(
    body: VoicePreviewRequest,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    """Generate short audio preview via TTS, upload to S3, return URL (signed if private)."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="TTS not configured. Set OPENAI_API_KEY.",
        )
    voice_id = (body.providerVoiceId or (str(body.voiceId) if body.voiceId else None)) or "alloy"
    sample = (body.text or "Hello, this is a short preview of this voice.").strip()[:500]
    try:
        audio_bytes = tts_synthesize(sample, voice_id=voice_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    key = voice_preview_key(workspace.id, voice_id)
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        upload_bytes(key, audio_bytes, "audio/mpeg")
        preview_url = presigned_url(key, expiration=3600)
    else:
        preview_url = "https://example.com/preview.mp3"

    return VoicePreviewResponse(previewUrl=preview_url)
