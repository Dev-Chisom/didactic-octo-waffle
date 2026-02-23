from __future__ import annotations

import os
import subprocess
import tempfile
import uuid
import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.base import SessionLocal
from app.db.models.asset import Asset
from app.db.models.episode import Episode
from app.services.storage_service import get_download_url, upload_file
from app.workers.celery_app import celery_app

FPS_OUT = 30


def _download_asset_url(url: str) -> bytes:
    if url.startswith("https://") or url.startswith("http://"):
        r = httpx.get(url, timeout=60, follow_redirects=True)
        r.raise_for_status()
        return r.content
    return b""


def _run_ffmpeg(cmd: list, timeout: int = 600) -> None:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as e:
        raise RuntimeError(
            "ffmpeg not found. Install it on the machine where the Celery worker runs: "
            "macOS: brew install ffmpeg — Linux: apt install ffmpeg"
        ) from e
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[:500]}")


def _ken_burns_segment(
    tmpdir: str,
    image_path: str | None,
    voice_path: str,
    duration: float,
    segment_path: str,
) -> None:
    fps_out = FPS_OUT
    num_frames = max(1, int(duration * fps_out))
    zoom_end = 1.2
    zoom_inc = (zoom_end - 1.0) / num_frames if num_frames else 0.0002
    zoom_expr = f"min(zoom+{zoom_inc:.6f},{zoom_end})"
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
        f"zoompan=z='{zoom_expr}':d=1:s=1080x1920:fps={fps_out}"
    )
    if image_path and os.path.isfile(image_path):
        cmd = [
            "ffmpeg", "-y", "-loop", "1", "-i", image_path,
            "-i", voice_path, "-shortest", "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", "-b:a", "128k",
            segment_path,
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"color=c=black:s=1080x1920:d={max(1, duration)}",
            "-i", voice_path, "-shortest",
            "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", "-b:a", "128k",
            segment_path,
        ]
    _run_ffmpeg(cmd)


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def render_video(self, episode_id: str):
    db: Session = SessionLocal()
    episode = None
    try:
        episode = db.query(Episode).filter(Episode.id == uuid.UUID(episode_id)).first()
        if not episode:
            raise ValueError(f"Episode {episode_id} not found")

        media = (episode.error or {}).get("media") if isinstance(episode.error, dict) else None
        if not media:
            raise ValueError("No media assets; run generate_media first")

        settings = get_settings()
        scenes = media.get("scenes")
        if scenes and len(scenes) >= 1:
            # --- Scene-based: render each segment then concat ---
            workspace_id = None
            with tempfile.TemporaryDirectory() as tmpdir:
                segment_paths = []
                total_duration = 0.0
                for idx, ref in enumerate(scenes):
                    voice_asset_id = ref.get("voice_asset_id")
                    if not voice_asset_id:
                        raise ValueError(f"Scene {idx} missing voice_asset_id")
                    voice_asset = db.query(Asset).filter(Asset.id == uuid.UUID(voice_asset_id)).first()
                    if not voice_asset:
                        raise ValueError(f"Voice asset {voice_asset_id} not found")
                    if workspace_id is None:
                        workspace_id = voice_asset.workspace_id
                    voice_url = get_download_url(voice_asset.url)
                    voice_data = _download_asset_url(voice_url)
                    if not voice_data:
                        raise ValueError(f"Could not download voice for scene {idx}")
                    voice_path = os.path.join(tmpdir, f"scene_{idx}_voice.mp3")
                    with open(voice_path, "wb") as f:
                        f.write(voice_data)
                    duration = float(ref.get("duration_seconds") or 5.0)
                    total_duration += duration

                    image_path = None
                    image_asset_id = ref.get("image_asset_id")
                    if image_asset_id:
                        image_asset = db.query(Asset).filter(
                            Asset.id == uuid.UUID(image_asset_id),
                            Asset.workspace_id == workspace_id,
                        ).first()
                        if image_asset:
                            image_data = _download_asset_url(get_download_url(image_asset.url))
                            if image_data:
                                image_path = os.path.join(tmpdir, f"scene_{idx}.png")
                                with open(image_path, "wb") as f:
                                    f.write(image_data)

                    seg_path = os.path.join(tmpdir, f"segment_{idx:04d}.mp4")
                    _ken_burns_segment(tmpdir, image_path, voice_path, duration, seg_path)
                    segment_paths.append(seg_path)

                if not segment_paths:
                    raise ValueError("No segments produced")

                # Concat demuxer
                list_file = os.path.join(tmpdir, "concat.txt")
                with open(list_file, "w") as f:
                    for p in segment_paths:
                        f.write(f"file '{p}'\n")
                out_mp4 = os.path.join(tmpdir, "out.mp4")
                concat_cmd = [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
                    "-c", "copy", out_mp4,
                ]
                _run_ffmpeg(concat_cmd)

                if not os.path.isfile(out_mp4):
                    raise RuntimeError("ffmpeg concat did not produce output")

                key = f"workspaces/{workspace_id}/episodes/{episode_id}/video.mp4"
                if settings.aws_access_key_id and settings.aws_secret_access_key:
                    with open(out_mp4, "rb") as f:
                        preview_url = upload_file(key, f, "video/mp4")
                else:
                    preview_url = f"https://storage.example.com/{key}"

            duration = total_duration
        else:
            # --- Legacy: single voice + optional single image ---
            voice_asset_id = media.get("voice_asset_id")
            if not voice_asset_id:
                raise ValueError("Missing voice_asset_id in media")
            voice_asset = db.query(Asset).filter(Asset.id == uuid.UUID(voice_asset_id)).first()
            if not voice_asset:
                raise ValueError(f"Voice asset {voice_asset_id} not found")
            workspace_id = voice_asset.workspace_id

            image_asset_id_raw = media.get("image_asset_id")
            image_asset = None
            if image_asset_id_raw:
                try:
                    image_asset = db.query(Asset).filter(
                        Asset.id == uuid.UUID(str(image_asset_id_raw)),
                        Asset.workspace_id == workspace_id,
                    ).first()
                except (ValueError, TypeError):
                    pass

            with tempfile.TemporaryDirectory() as tmpdir:
                voice_path = os.path.join(tmpdir, "voice.mp3")
                voice_data = _download_asset_url(get_download_url(voice_asset.url))
                if not voice_data:
                    raise ValueError("Could not download voice asset")
                with open(voice_path, "wb") as f:
                    f.write(voice_data)
                try:
                    out = subprocess.run(
                        [
                            "ffprobe", "-v", "error",
                            "-show_entries", "format=duration",
                            "-of", "default=noprint_wrappers=1:nokey=1",
                            voice_path,
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    duration = float(out.stdout.strip()) if out.returncode == 0 and out.stdout else 30.0
                except (FileNotFoundError, ValueError):
                    duration = 30.0

                image_path = None
                if image_asset:
                    image_data = _download_asset_url(get_download_url(image_asset.url))
                    if image_data:
                        image_path = os.path.join(tmpdir, "cover.png")
                        with open(image_path, "wb") as f:
                            f.write(image_data)
                out_mp4 = os.path.join(tmpdir, "out.mp4")
                _ken_burns_segment(tmpdir, image_path, voice_path, duration, out_mp4)
                if not os.path.isfile(out_mp4):
                    raise RuntimeError("ffmpeg did not produce output file")
                key = f"workspaces/{workspace_id}/episodes/{episode_id}/video.mp4"
                if settings.aws_access_key_id and settings.aws_secret_access_key:
                    with open(out_mp4, "rb") as f:
                        preview_url = upload_file(key, f, "video/mp4")
                else:
                    preview_url = f"https://storage.example.com/{key}"

        video_asset = Asset(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            type="video",
            source="generated",
            url=preview_url,
            format="video/mp4",
            duration_seconds=duration,
            metadata_={"episode_id": episode_id},
        )
        db.add(video_asset)
        db.flush()

        episode.video_asset_id = video_asset.id
        episode.preview_url = preview_url
        episode.status = "ready_for_review"
        episode.error = None
        db.commit()

        return {
            "episode_id": episode_id,
            "status": "ok",
            "video_asset_id": str(video_asset.id),
            "preview_url": preview_url,
        }
    except Exception as e:
        if episode:
            existing = (episode.error or {}) if isinstance(episode.error, dict) else {}
            episode.error = {**existing, "step": "render", "message": str(e)}
            db.commit()
        raise
    finally:
        db.close()
