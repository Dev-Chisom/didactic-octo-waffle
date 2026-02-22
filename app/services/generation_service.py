import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.episode import Episode, Script
from app.db.models.series import Series
from app.services.llm_service import generate_script_scenes, generate_script_text


def _build_script_from_scenes(scenes: list) -> str:
    return "\n\n".join((s.get("text") or "").strip() for s in scenes)


def run_script_generation(db: Session, episode_id: uuid.UUID) -> dict[str, Any]:
    episode = db.query(Episode).filter(Episode.id == episode_id).first()
    if not episode:
        raise ValueError("Episode not found")
    series = db.query(Series).filter(Series.id == episode.series_id).first()
    if not series:
        raise ValueError("Series not found")

    episode.status = "generating"
    db.commit()

    voice_language = series.voice_language or {}
    language_code = voice_language.get("languageCode", "en-US")
    settings = get_settings()

    if settings.use_scene_based_video:
        scenes = generate_script_scenes(
            content_type=series.content_type,
            custom_topic=series.custom_topic,
            script_preferences=series.script_preferences,
            language_code=language_code,
            num_scenes_min=settings.video_scenes_min,
            num_scenes_max=settings.video_scenes_max,
        )
        script_text = _build_script_from_scenes(scenes)
        scenes_payload = [
            {"scene": s["scene"], "text": s["text"], "visual_description": s["visual_description"]}
            for s in scenes
        ]
    else:
        script_text = generate_script_text(
            content_type=series.content_type,
            custom_topic=series.custom_topic,
            script_preferences=series.script_preferences,
            language_code=language_code,
        )
        scenes_payload = None

    script = Script(
        id=uuid.uuid4(),
        series_id=series.id,
        language_code=language_code,
        text=script_text,
        scenes=scenes_payload,
        prompt_metadata={
            "content_type": series.content_type,
            "custom_topic": series.custom_topic,
            "script_preferences": series.script_preferences,
        },
    )
    db.add(script)
    db.flush()

    episode.script_id = script.id
    episode.status = "ready_for_review"
    episode.error = None
    db.commit()
    db.refresh(episode)

    return {
        "episode_id": str(episode.id),
        "script_id": str(script.id),
        "status": episode.status,
        "script_length": len(script_text),
        "scene_count": len(scenes_payload) if scenes_payload else None,
    }
