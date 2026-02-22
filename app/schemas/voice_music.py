"""Voice and music API schemas."""

from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class VoicePreviewRequest(BaseModel):
    text: str
    languageCode: str
    voiceId: Optional[UUID] = None
    providerVoiceId: Optional[str] = None  # e.g. "alloy", "nova" for OpenAI TTS
    gender: Optional[str] = None
    style: Optional[str] = None
    speed: Optional[float] = Field(None, ge=0, le=2)
    pitch: Optional[float] = Field(None, ge=0, le=2)


class VoicePreviewResponse(BaseModel):
    previewUrl: str


class VoiceItem(BaseModel):
    id: str
    name: str
    languageCode: str
    gender: str
    style: str
    isPremium: bool = False
    previewUrl: Optional[str] = None


class MusicPresetItem(BaseModel):
    id: str
    mood: str
    name: str
    sampleUrl: Optional[str] = None


class MusicLibraryItem(BaseModel):
    id: UUID
    mood: str
    name: str
    durationSeconds: float
    url: Optional[str] = None
