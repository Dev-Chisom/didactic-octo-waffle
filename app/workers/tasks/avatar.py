from __future__ import annotations

import logging
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import SessionLocal
from app.db.models.asset import Asset
from app.db.models.episode import Episode
from app.db.models.series import Series
from app.services.lipsync import LipSyncError, run_lipsync_sync
from app.services.avatar_service import ensure_series_avatar_image_url
from app.services.storage_service import upload_bytes, upload_file, get_download_url
from app.services.tts_service import synthesize as tts_synthesize
from app.workers.celery_app import celery_app


logger = logging.getLogger(__name__)


def _voice_id_from_series(voice_language: dict | None) -> str:
    if not voice_language:
        return "alloy"
    gender = (voice_language.get("gender") or "").lower()
    style = (voice_language.get("style") or "").lower()
    if "female" in gender:
        return "nova" if "warm" in style else "shimmer"
    if "male" in gender:
        return "onyx" if "deep" in style else "echo"
    return "alloy"


def _convert_mp3_to_normalized_wav16_mono(
    mp3_bytes: bytes,
    sample_rate: int = 16000,
) -> bytes:
    """
    Convert arbitrary MP3 bytes to normalized 16-bit PCM WAV mono at the given sample rate.

    Uses ffmpeg so we match the expectations of most lip-sync models.
    """
    settings = get_settings()
    ffmpeg_bin = "ffmpeg"  # rely on system ffmpeg (same as render pipeline)

    with tempfile.TemporaryDirectory() as tmpdir:
        in_path = Path(tmpdir) / "in.mp3"
        out_path = Path(tmpdir) / "out.wav"
        in_path.write_bytes(mp3_bytes)
        cmd = [
            ffmpeg_bin,
            "-y",
            "-i",
            str(in_path),
            "-ac",
            "1",  # mono
            "-ar",
            str(sample_rate),
            "-sample_fmt",
            "s16",
            "-af",
            "loudnorm",
            str(out_path),
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except FileNotFoundError as e:
            raise RuntimeError(
                "ffmpeg not found. Install it on the machine where the Celery worker runs."
            ) from e
        if result.returncode != 0 or not out_path.is_file():
            raise RuntimeError(f"ffmpeg audio normalize/convert failed: {result.stderr[:500]}")
        return out_path.read_bytes()


def _validate_avatar_image(url: str) -> None:
    """
    Basic validation for avatar image requirements:
    - Reasonable resolution (height >= 512).
    - Roughly 9:16 aspect ratio (within a tolerance).

    We cannot automatically guarantee mouth visibility or front-facing pose, so we
    rely on manual curation there.
    """
    # Best-effort client-side validation. If our network cannot reach the host,
    # log a warning but do not block the pipeline – Replicate will fetch the URL
    # from its own environment during lip-sync.
    try:
        resp = httpx.get(url, timeout=30.0, follow_redirects=True)
    except httpx.RequestError as e:
        logger.warning("Skipping avatar image validation due to network error: %s", e)
        return

    if resp.status_code != 200:
        logger.warning(
            "Skipping avatar image validation due to HTTP status %s for url=%s",
            resp.status_code,
            url,
        )
        return

    from PIL import Image
    from io import BytesIO

    im = Image.open(BytesIO(resp.content))
    w, h = im.size
    if h < 512:
        raise ValueError("Avatar image too small; height must be at least 512px.")
    aspect = h / float(w or 1)
    target = 16 / 9
    if abs(aspect - target) > 0.2:
        raise ValueError("Avatar image should be close to 9:16 aspect ratio for best framing.")


@celery_app.task(
    bind=True,
    # Network/HTTP issues are retried; LipSyncError (model timeout/failure) is not,
    # to avoid re-running the whole avatar pipeline from scratch on long/failed runs.
    autoretry_for=(ConnectionError, TimeoutError, httpx.RequestError, httpx.HTTPError),
    retry_backoff=True,
    max_retries=3,
)
def generate_avatar_video(self, episode_id: str):
    """
    Avatar pipeline:
    - Fetch episode, series, script.
    - Generate narration audio (OpenAI TTS) if not already present.
    - Convert audio to 16-bit PCM WAV mono at 16kHz and normalize.
    - Upload WAV to S3 and obtain a URL.
    - Call Replicate lip-sync and poll until completion.
    - Download generated MP4 and upload to S3.
    - Attach resulting video as the episode.preview_url / video_asset_id.
    """
    db: Session = SessionLocal()
    episode: Optional[Episode] = None
    try:
        settings = get_settings()
        if not settings.enable_avatar_mode:
            # Fail fast if avatar mode is not enabled via feature flag.
            raise ValueError("Avatar mode is disabled (ENABLE_AVATAR_MODE=false).")

        episode = db.query(Episode).filter(Episode.id == uuid.UUID(episode_id)).first()
        if not episode:
            raise ValueError(f"Episode {episode_id} not found")
        series = db.query(Series).filter(Series.id == episode.series_id).first()
        if not series:
            raise ValueError("Series not found")
        if not episode.script_id or not episode.script or not episode.script.text:
            raise ValueError("Episode has no script text")

        episode.lipsync_status = "PROCESSING"
        db.commit()

        # Ensure we have an avatar image for this series; generate via SDXL if missing.
        avatar_image_url = ensure_series_avatar_image_url(db, series)
        # Use a presigned URL when S3 is private, so both our validator and Replicate
        # can fetch the image.
        avatar_fetch_url = get_download_url(avatar_image_url, expiration=3600)
        _validate_avatar_image(avatar_fetch_url)

        workspace_id = series.workspace_id
        voice_id = _voice_id_from_series(series.voice_language)

        # TTS (MP3 bytes) – reuse existing OpenAI TTS integration.
        tts_bytes = tts_synthesize(episode.script.text, voice_id=voice_id)
        wav_bytes = _convert_mp3_to_normalized_wav16_mono(tts_bytes, sample_rate=16000)

        # Upload WAV to S3 (or placeholder URL when S3 is disabled).
        key_audio = f"workspaces/{workspace_id}/episodes/{episode_id}/avatar_voice.wav"
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            audio_canonical_url = upload_bytes(key_audio, wav_bytes, "audio/wav")
            audio_url = get_download_url(audio_canonical_url, expiration=3600)
        else:
            audio_url = f"https://storage.example.com/{key_audio}"

        # Temporary: allow disabling lip-sync entirely via env so the pipeline
        # still produces episodes without blocking on Replicate.
        if not settings.enable_avatar_lipsync:
            episode.lipsync_status = "SKIPPED"
            episode.status = "ready_for_review"
            existing_error = episode.error or {}
            if not isinstance(existing_error, dict):
                existing_error = {}
            existing_error["avatar"] = {
                "audio_url": audio_url,
                "lipsync_source_url": None,
                "video_asset_id": None,
                "note": "Avatar lipsync disabled (ENABLE_AVATAR_LIPSYNC=false).",
            }
            episode.error = existing_error
            db.commit()
            return {
                "episode_id": str(episode.id),
                "status": "avatar_audio_only",
                "audio_url": audio_url,
            }

        # Call Replicate lip-sync (timeout and poll interval from config; lip-sync is GPU-heavy and slow).
        lipsync_video_url = run_lipsync_sync(
            face_image_url=avatar_fetch_url,
            audio_url=audio_url,
            timeout_seconds=settings.replicate_lipsync_timeout_seconds,
            poll_interval_seconds=settings.replicate_lipsync_poll_interval_seconds,
        )

        # Download generated MP4 and upload to our S3.
        resp = httpx.get(lipsync_video_url, timeout=300.0, follow_redirects=True)
        resp.raise_for_status()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "avatar_talking.mp4"
            tmp_path.write_bytes(resp.content)

            key_video = f"workspaces/{workspace_id}/episodes/{episode_id}/avatar_talking.mp4"
            if settings.aws_access_key_id and settings.aws_secret_access_key:
                with open(tmp_path, "rb") as f:
                    final_url = upload_file(key_video, f, "video/mp4")
            else:
                final_url = f"https://storage.example.com/{key_video}"

        # Persist as an Asset and link to Episode.
        video_asset = Asset(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            type="video",
            source="generated",
            url=final_url,
            format="video/mp4",
            duration_seconds=None,
            metadata_={"episode_id": episode_id, "role": "avatar_base"},
        )
        db.add(video_asset)
        db.flush()

        episode.video_asset_id = video_asset.id
        episode.preview_url = final_url
        episode.avatar_video_url = final_url
        episode.lipsync_status = "DONE"
        episode.status = "ready_for_review"
        existing_error = episode.error or {}
        if not isinstance(existing_error, dict):
            existing_error = {}
        existing_error["avatar"] = {
            "audio_url": audio_url,
            "lipsync_source_url": lipsync_video_url,
            "video_asset_id": str(video_asset.id),
        }
        episode.error = existing_error
        db.commit()

        return {
            "episode_id": episode_id,
            "status": "ok",
            "video_asset_id": str(video_asset.id),
            "preview_url": final_url,
        }
    except Exception as e:
        if episode:
            episode.lipsync_status = "FAILED"
            existing_error = episode.error or {}
            if not isinstance(existing_error, dict):
                existing_error = {}
            existing_error["avatar_error"] = {"message": str(e)}
            episode.error = existing_error
            db.commit()
        raise
    finally:
        db.close()

