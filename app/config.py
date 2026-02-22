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

    # Social OAuth
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    instagram_client_id: str = ""
    instagram_client_secret: str = ""
    youtube_client_id: str = ""
    youtube_client_secret: str = ""
    facebook_app_id: str = ""
    facebook_app_secret: str = ""

    # TTS
    openai_tts_model: str = "tts-1"
    elevenlabs_api_key: str = ""

    # Video image
    openai_generate_video_image: bool = True
    openai_image_model: str = "dall-e-3"

    # Scene-based video
    use_scene_based_video: bool = True
    video_scenes_min: int = 5
    video_scenes_max: int = 12

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

    @property
    def celery_broker(self) -> str:
        return self.celery_broker_url or self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
