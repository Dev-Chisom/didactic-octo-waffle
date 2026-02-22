"""Series and wizard step schemas."""

from typing import Any, Optional, Union
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


# ---- Step 1: Content type ----
class CustomTopicSchema(BaseModel):
    topicTitle: Optional[str] = None
    targetAudience: Optional[str] = None
    tone: Optional[str] = None
    keywords: Optional[list[str]] = None
    ctaStyle: Optional[str] = None


class SeriesCreateBody(BaseModel):
    name: Optional[str] = None
    contentType: str  # motivation, horror, finance, ai_tech, kids, anime, custom
    customTopic: Optional[CustomTopicSchema] = None


class Step1ContentTypeUpdate(BaseModel):
    name: Optional[str] = None
    contentType: Optional[str] = None
    customTopic: Optional[CustomTopicSchema] = None


# ---- Step 2: Script preferences ----
class Step2ScriptPreferencesUpdate(BaseModel):
    storyLength: Optional[str] = None  # 30_40, 45_60
    tone: Optional[str] = None
    hookStrength: Optional[str] = None
    includeCta: Optional[bool] = None
    ctaText: Optional[str] = None


# ---- Step 3: Voice & language ----
class Step3VoiceLanguageUpdate(BaseModel):
    languageCode: Optional[str] = None
    gender: Optional[str] = None  # male, female, neutral
    style: Optional[str] = None
    speed: Optional[float] = Field(None, ge=0, le=2)
    pitch: Optional[float] = Field(None, ge=0, le=2)


# ---- Step 4: Music ----
class Step4MusicUpdate(BaseModel):
    mode: Optional[str] = None  # preset, library, custom
    presetMood: Optional[str] = None
    libraryTrackId: Optional[UUID] = None
    customUploadAssetId: Optional[UUID] = None
    tiktokUrl: Optional[str] = None


# ---- Step 5: Art style ----
class ColorThemeSchema(BaseModel):
    primary: Optional[str] = None
    accent: Optional[str] = None
    background: Optional[str] = None


class Step5ArtStyleUpdate(BaseModel):
    """Accepts both FE names (artStyle, artIntensity) and backend names (style, intensity)."""

    style: Optional[str] = Field(None, alias="artStyle")
    intensity: Optional[float] = Field(None, ge=0, le=1, alias="artIntensity")
    colorTheme: Optional[ColorThemeSchema] = None

    model_config = {"populate_by_name": True}

    @field_validator("intensity", mode="before")
    @classmethod
    def normalize_intensity(cls, v):
        """Accept 0-1 or 0-100 (percentage) and normalize to 0-1."""
        if v is None:
            return None
        try:
            x = float(v)
        except (TypeError, ValueError):
            return v
        if 0 <= x <= 1:
            return x
        if 0 <= x <= 100:
            return x / 100.0
        return v


# ---- Step 6: Caption style ----
class Step6CaptionStyleUpdate(BaseModel):
    style: Optional[str] = None
    fontFamily: Optional[str] = None
    fontColor: Optional[str] = None
    highlightColor: Optional[str] = None
    position: Optional[str] = None  # top, middle, bottom
    backgroundEnabled: Optional[bool] = None


# ---- Step 7: Effects ----
class EffectItemSchema(BaseModel):
    type: str
    enabled: bool = True
    isPremium: bool = False
    params: Optional[dict] = None


class Step7EffectsUpdate(BaseModel):
    """Accepts either array or object for effects (FE sends effects as object keyed by name).
    
    Frontend format: { "effects": { "animatedHook": { enabled, isPremium }, "filmGrain": { enabled }, ... } }
    Or top-level: { "animatedHook": { enabled }, "filmGrain": { enabled }, ... }
    Backend array format: { "effects": [{ type: "animatedHook", enabled, isPremium }, ...] }
    """
    effects: Optional[Union[list[EffectItemSchema], dict[str, Any]]] = None

    model_config = {"extra": "allow"}


# ---- Step 8: Social ----
class Step8SocialUpdate(BaseModel):
    """FE sends connectedAccountIds (string[]); backend stores as socialAccountIds."""
    socialAccountIds: Optional[list[UUID]] = None
    connectedAccountIds: Optional[list[UUID]] = None  # FE alias; use if socialAccountIds not set

    model_config = {"extra": "allow"}


# ---- Step 9: Schedule ----
class Step9ScheduleUpdate(BaseModel):
    videoDuration: Optional[str] = None  # 30_40, 45_60
    frequency: Optional[str] = None  # daily, 3x_per_week, custom
    customDays: Optional[list[int]] = None  # weekdays 0-6
    publishTime: Optional[str] = None  # time string
    timezone: Optional[str] = None
    startDate: Optional[str] = None  # date string
    active: Optional[bool] = None


# ---- Series response ----
class SeriesResponse(BaseModel):
    id: UUID
    workspaceId: UUID
    name: str
    contentType: str
    customTopic: Optional[dict] = None
    scriptPreferences: Optional[dict] = None
    voiceLanguage: Optional[dict] = None
    musicSettings: Optional[dict] = None
    artStyle: Optional[dict] = None
    captionStyle: Optional[dict] = None
    visualEffects: Optional[list] = None
    schedule: Optional[dict] = None
    status: str
    estimatedCreditsPerVideo: Optional[float] = None
    autoPostEnabled: bool
    connectedSocialAccountIds: Optional[list] = None
    createdAt: str
    updatedAt: str

    model_config = {"from_attributes": True}


class LaunchSeriesResponse(BaseModel):
    series: SeriesResponse
    upcomingEpisodes: list[dict]
    creditEstimate: dict
