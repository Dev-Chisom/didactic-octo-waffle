from __future__ import annotations

import subprocess
import tempfile
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import SessionLocal
from app.db.models.asset import Asset
from app.db.models.episode import Episode, Script
from app.db.models.series import Series
from app.services.image_service import generate_scene_image, generate_video_image
from app.services.storage_service import upload_bytes
from app.services.tts_service import synthesize as tts_synthesize
from app.workers.celery_app import celery_app


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


def _probe_duration_seconds(audio_bytes: bytes) -> float:
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(audio_bytes)
            path = f.name
        try:
            out = subprocess.run(
                [
                    "ffprobe",
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    path,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if out.returncode == 0 and out.stdout:
                return float(out.stdout.strip())
        finally:
            Path(path).unlink(missing_ok=True)
    except Exception:
        pass
    return 5.0


def _resolve_music_asset(db: Session, series: Series, workspace_id: uuid.UUID) -> uuid.UUID | None:
    music_settings = series.music_settings or {}
    for key in ("customUploadAssetId", "libraryTrackId"):
        aid_str = music_settings.get(key)
        if not aid_str:
            continue
        try:
            aid = uuid.UUID(aid_str)
            existing = db.query(Asset).filter(
                Asset.id == aid, Asset.workspace_id == workspace_id, Asset.type == "music"
            ).first()
            if existing:
                return existing.id
        except (ValueError, TypeError):
            pass
    return None


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def generate_media(self, episode_id: str):
    db: Session = SessionLocal()
    episode = None
    try:
        episode = db.query(Episode).filter(Episode.id == uuid.UUID(episode_id)).first()
        if not episode:
            raise ValueError(f"Episode {episode_id} not found")
        series = db.query(Series).filter(Series.id == episode.series_id).first()
        if not series:
            raise ValueError(f"Series not found")
        script = db.query(Script).filter(Script.id == episode.script_id).first() if episode.script_id else None
        if not script or not script.text:
            raise ValueError("Episode has no script text")

        settings = get_settings()
        workspace_id = series.workspace_id
        meta = {"episode_id": episode_id}
        voice_id = _voice_id_from_series(series.voice_language)
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY required for TTS")

        use_scenes = (
            settings.use_scene_based_video
            and script.scenes
            and len(script.scenes) >= 1
        )

        if use_scenes:
            # Scene-based pipeline: N TTS + N images per scene
            scene_refs = []
            for idx, scene in enumerate(script.scenes):
                text = (scene.get("text") or "").strip()
                vis = (scene.get("visual_description") or text[:500]).strip()
                if not text:
                    raise ValueError(f"Scene {idx + 1} has no text")
                audio_bytes = tts_synthesize(text, voice_id=voice_id)
                duration = _probe_duration_seconds(audio_bytes)
                key_voice = f"workspaces/{workspace_id}/episodes/{episode_id}/scene_{idx}_voice.mp3"
                if settings.aws_access_key_id and settings.aws_secret_access_key:
                    url_voice = upload_bytes(key_voice, audio_bytes, "audio/mpeg")
                else:
                    url_voice = f"https://storage.example.com/{key_voice}"
                voice_asset = Asset(
                    id=uuid.uuid4(),
                    workspace_id=workspace_id,
                    type="audio",
                    source="generated",
                    url=url_voice,
                    format="audio/mpeg",
                    duration_seconds=duration,
                    metadata_={**meta, "role": "scene_voice", "scene_index": idx},
                )
                db.add(voice_asset)
                db.flush()
                image_asset_id = None
                image_bytes = generate_scene_image(vis, scene_index=idx)
                if image_bytes and settings.aws_access_key_id and settings.aws_secret_access_key:
                    key_image = f"workspaces/{workspace_id}/episodes/{episode_id}/scene_{idx}.png"
                    url_image = upload_bytes(key_image, image_bytes, "image/png")
                    img_asset = Asset(
                        id=uuid.uuid4(),
                        workspace_id=workspace_id,
                        type="image",
                        source="generated",
                        url=url_image,
                        format="image/png",
                        duration_seconds=None,
                        metadata_={**meta, "role": "scene_cover", "scene_index": idx},
                    )
                    db.add(img_asset)
                    db.flush()
                    image_asset_id = str(img_asset.id)
                scene_refs.append({
                    "image_asset_id": image_asset_id,
                    "voice_asset_id": str(voice_asset.id),
                    "duration_seconds": duration,
                })
            caption_asset = Asset(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                type="caption_file",
                source="generated",
                url="",
                format="srt",
                duration_seconds=None,
                metadata_={**meta, "text": script.text[:2000]},
            )
            db.add(caption_asset)
            db.flush()
            music_asset_id = _resolve_music_asset(db, series, workspace_id)
            episode.error = {
                "media": {
                    "scenes": scene_refs,
                    "caption_asset_id": str(caption_asset.id),
                    "music_asset_id": str(music_asset_id) if music_asset_id else None,
                }
            }
            episode.status = "generating"
            db.commit()
            from app.workers.tasks.render import render_video
            render_video.delay(episode_id)
            return {
                "episode_id": episode_id,
                "status": "ok",
                "scene_count": len(scene_refs),
                "caption_asset_id": str(caption_asset.id),
            }

        # Legacy: single voice + single image
        audio_bytes = tts_synthesize(script.text, voice_id=voice_id)
        key_voice = f"workspaces/{workspace_id}/episodes/{episode_id}/voice.mp3"
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            url_voice = upload_bytes(key_voice, audio_bytes, "audio/mpeg")
        else:
            url_voice = f"https://storage.example.com/{key_voice}"
        voice_asset = Asset(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            type="audio",
            source="generated",
            url=url_voice,
            format="audio/mpeg",
            duration_seconds=None,
            metadata_={**meta, "role": "voice"},
        )
        db.add(voice_asset)
        db.flush()
        music_asset_id = _resolve_music_asset(db, series, workspace_id)
        caption_asset = Asset(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            type="caption_file",
            source="generated",
            url="",
            format="srt",
            duration_seconds=None,
            metadata_={**meta, "text": script.text[:2000]},
        )
        db.add(caption_asset)
        db.flush()
        image_asset_id = None
        image_bytes = generate_video_image(script.text)
        if image_bytes and settings.aws_access_key_id and settings.aws_secret_access_key:
            key_image = f"workspaces/{workspace_id}/episodes/{episode_id}/cover.png"
            url_image = upload_bytes(key_image, image_bytes, "image/png")
            image_asset = Asset(
                id=uuid.uuid4(),
                workspace_id=workspace_id,
                type="image",
                source="generated",
                url=url_image,
                format="image/png",
                duration_seconds=None,
                metadata_={**meta, "role": "video_cover"},
            )
            db.add(image_asset)
            db.flush()
            image_asset_id = str(image_asset.id)
        episode.error = {
            "media": {
                "voice_asset_id": str(voice_asset.id),
                "music_asset_id": str(music_asset_id) if music_asset_id else None,
                "caption_asset_id": str(caption_asset.id),
                "image_asset_id": image_asset_id,
            }
        }
        episode.status = "generating"
        db.commit()
        from app.workers.tasks.render import render_video
        render_video.delay(episode_id)
        return {
            "episode_id": episode_id,
            "status": "ok",
            "voice_asset_id": str(voice_asset.id),
            "music_asset_id": str(music_asset_id) if music_asset_id else None,
            "caption_asset_id": str(caption_asset.id),
        }
    except Exception as e:
        if episode:
            episode.status = "failed"
            episode.error = {"step": "media_generation", "message": str(e)}
            db.commit()
        raise
    finally:
        db.close()
