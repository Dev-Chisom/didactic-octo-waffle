from functools import lru_cache
from typing import List, Literal, Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "AI Series Dashboard API"
    debug: bool = False
    environment: Literal["development", "staging", "production"] = "development"

    # API
    api_v1_prefix: str = "/api/v1"

    # DB
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/auto_viral"
    database_url_async: Optional[str] = None

    # JWT
    secret_key: str = "change-me-in-production-use-env"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Celery
    celery_broker_url: Optional[str] = None

    # S3
    s3_bucket: str = Field(
        default="viral-video-som",
        validation_alias=AliasChoices("S3_BUCKET", "S3_BUCKET_NAME"),
    )
    s3_region: str = Field(
        default="eu-west-1",
        validation_alias=AliasChoices("S3_REGION", "AWS_REGION"),
    )
    s3_endpoint_url: Optional[str] = None
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_publishable_key: str = ""

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: Optional[str] = None

    # Frontend
    cors_origins: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    frontend_url: str = "http://localhost:3000"
    public_base_url: Optional[str] = Field(
        default=None,
        description="Public-facing base URL for OAuth redirects (scheme + host).",
        validation_alias=AliasChoices("PUBLIC_BASE_URL", "BACKEND_PUBLIC_URL", "API_PUBLIC_BASE_URL"),
    )

    # Google OAuth (login)
    google_client_id: str = ""
    google_client_secret: str = ""

    # Social OAuth
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    tiktok_scopes: str = Field(
        default="user.info.basic,video.list,video.upload",
        validation_alias=AliasChoices("TIKTOK_SCOPES", "TIKTOK_OAUTH_SCOPES"),
    )
    instagram_client_id: str = ""
    instagram_client_secret: str = ""
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    facebook_app_id: str = ""
    facebook_app_secret: str = ""

    # TTS
    openai_tts_model: str = "tts-1"
    elevenlabs_api_key: str = Field(
        default="",
        validation_alias="ELEVENLABS_API_KEY",
        description="ElevenLabs API key (from https://elevenlabs.io/app/settings/api-keys).",
    )
    tts_provider: Literal["openai", "elevenlabs"] = Field(
        default="openai",
        validation_alias=AliasChoices("TTS_PROVIDER", "TTS_ENGINE"),
        description="Global TTS provider: 'openai' or 'elevenlabs'.",
    )
    elevenlabs_voice_id: str = Field(
        default="",
        validation_alias="ELEVENLABS_VOICE_ID",
        description="Default ElevenLabs voice id to use for TTS.",
    )
    elevenlabs_model_id: str = Field(
        default="eleven_multilingual_v2",
        validation_alias="ELEVENLABS_MODEL_ID",
        description=(
            "ElevenLabs TTS model id. Supported: eleven_v3 (5k chars), eleven_multilingual_v2 (10k), "
            "eleven_flash_v2_5 / eleven_turbo_v2_5 (40k). Deprecated: eleven_monolingual_v1, eleven_multilingual_v1."
        ),
    )
    elevenlabs_base_url: str = Field(
        default="https://api.elevenlabs.io/v1",
        validation_alias="ELEVENLABS_BASE_URL",
        description="ElevenLabs API base URL (e.g. https://api.elevenlabs.io/v1).",
    )

    # Image generation (Replicate primary, Pexels fallback)
    replicate_api_token: str = ""
    replicate_model_version: str = Field(
        default="a00d0b7dcbb9c3fbb34ba87d2d5b46c56969c84a628bf778a7fdaec30b1b99c5",
        description="Replicate SDXL model version (stability-ai/sdxl)",
    )
    # Avatar lip-sync (Replicate hosted model)
    enable_avatar_lipsync: bool = Field(
        default=True,
        validation_alias="ENABLE_AVATAR_LIPSYNC",
        description="When false, skip Replicate lip-sync and only generate avatar audio/image.",
    )
    replicate_lipsync_model_version: str = Field(
        default="",
        validation_alias="REPLICATE_LIPSYNC_MODEL_VERSION",
        description="Replicate model version for avatar lip-sync (username/model:hash).",
    )
    replicate_lipsync_timeout_seconds: int = Field(
        default=600,
        validation_alias="REPLICATE_LIPSYNC_TIMEOUT_SECONDS",
        description="Max seconds to wait for Replicate lip-sync (GPU-heavy; 5–10s audio ≈ 1 min, 60s audio ≈ 3–6 min).",
    )
    replicate_lipsync_poll_interval_seconds: float = Field(
        default=3.0,
        validation_alias="REPLICATE_LIPSYNC_POLL_INTERVAL_SECONDS",
        description="Seconds between Replicate prediction polls (e.g. 3 to avoid hammering the API).",
    )
    pexels_api_key: str = ""

    # Scene-based video
    use_scene_based_video: bool = True
    video_scenes_min: int = 5
    video_scenes_max: int = 12

    # Reel engine (story.py): when True, script generation uses reel_engine build_story_plan (style/topic/narration LLM or templates)
    use_reel_engine_story: bool = True
    reel_engine_cache_dir: Optional[str] = None  # Narration cache; None = no disk cache

    # Email
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@example.com"
    smtp_use_tls: bool = True
    password_reset_link_path: str = "/reset-password"

    # Feature flags
    feature_flags: str = ""
    enable_avatar_mode: bool = Field(
        default=False,
        validation_alias="ENABLE_AVATAR_MODE",
        description="Enable avatar-based pipeline (lip-sync + talking head) instead of legacy Ken Burns video.",
    )

    @property
    def celery_broker(self) -> str:
        return self.celery_broker_url or self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
