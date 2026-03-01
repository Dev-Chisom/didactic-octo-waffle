import uuid
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models.episode import Episode, Script
from app.db.models.series import Series
from app.services.llm_service import generate_script_scenes, generate_script_text


def _build_script_from_scenes(scenes: list) -> str:
    return "\n\n".join((s.get("text") or "").strip() for s in scenes)


def _reel_style_from_series(series: Series) -> str:
    """Map series content_type / art_style to reel_engine style (horror, crime, cartoon, anime, faceless)."""
    art = (series.art_style or {}).get("style") if isinstance(series.art_style, dict) else None
    if art and str(art).lower() in ("horror", "crime", "cartoon", "anime", "faceless"):
        return str(art).lower()
    ct = (series.content_type or "").lower()
    if ct == "horror":
        return "horror"
    if ct == "anime":
        return "anime"
    if ct == "kids":
        return "cartoon"
    return "faceless"


def _topic_from_series(series: Series) -> str:
    """Topic for reel_engine: custom topic title, or series name."""
    custom = series.custom_topic or {}
    if isinstance(custom, dict):
        title = (custom.get("topicTitle") or "").strip()
        if title:
            return title
    return (series.name or "untitled story").strip() or "untitled story"


def _duration_sec_from_series(series: Series) -> float:
    """Duration in seconds from script_preferences.storyLength."""
    prefs = series.script_preferences or {}
    if not isinstance(prefs, dict):
        return 45.0
    length = prefs.get("storyLength") or ""
    if length == "30_40":
        return 35.0
    if length == "45_60":
        return 50.0
    if length == "2_3_min":
        return 150.0
    return 45.0


def _episode_context(db: Session, episode: Episode) -> tuple[int, int, Optional[str]]:
    """(episode_index, total_episodes, previous_episode_summary). Pairs (1,2), (3,4), ... are 2-part stories."""
    all_episodes = (
        db.query(Episode)
        .filter(Episode.series_id == episode.series_id)
        .order_by(Episode.sequence_number.asc())
        .all()
    )
    if not all_episodes:
        return 1, 1, None

    pos = 0
    for i, ep in enumerate(all_episodes):
        if ep.id == episode.id:
            pos = i
            break

    is_second_in_pair = pos % 2 == 1
    has_pair = pos + 1 < len(all_episodes) if pos % 2 == 0 else True

    if not has_pair:
        return 1, 1, None

    if not is_second_in_pair:
        return 1, 2, None

    prev_ep = all_episodes[pos - 1]
    if not prev_ep.script_id:
        return 2, 2, None

    prev_script = db.query(Script).filter(Script.id == prev_ep.script_id).first()
    if not prev_script or not (prev_script.text or "").strip():
        return 2, 2, None

    text = (prev_script.text or "").strip()
    summary = text[-500:] if len(text) > 500 else text
    return 2, 2, summary


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

    episode_index, total_episodes, previous_episode_summary = _episode_context(db, episode)

    if getattr(settings, "use_reel_engine_story", False):
        try:
            from reel_engine.story import build_story_plan
        except ImportError:
            pass  # fall through to LLM path below
        else:
            style = _reel_style_from_series(series)
            topic = _topic_from_series(series)
            duration_sec = _duration_sec_from_series(series)
            cache_dir = None
            if getattr(settings, "reel_engine_cache_dir", None):
                cache_dir = Path(settings.reel_engine_cache_dir)
            plan = build_story_plan(
                style=style,
                topic=topic,
                duration_sec=duration_sec,
                part_index=episode_index,
                parts_total=max(1, total_episodes),
                cache_dir=cache_dir,
                previous_part_summary=previous_episode_summary,
            )
            script_text = "\n".join(s.narration_text for s in plan.shots)
            scenes_payload = [
                {
                    "scene": s.id,
                    "text": s.narration_text,
                    "visual_description": s.visual_beat,
                    "duration_seconds": s.duration_sec,
                }
                for s in plan.shots
            ]
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
                    "source": "reel_engine",
                    "style": plan.style,
                    "topic": plan.topic,
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
                "scene_count": len(scenes_payload),
            }

    if settings.use_scene_based_video:
        prefs = series.script_preferences or {}
        sl = prefs.get("storyLength", "30_40") if isinstance(prefs, dict) else "30_40"
        if sl == "2_3_min":
            scene_min, scene_max = 12, 24  # 2-3 min needs more scenes
        else:
            scene_min = settings.video_scenes_min
            scene_max = settings.video_scenes_max
        scenes = generate_script_scenes(
            content_type=series.content_type,
            custom_topic=series.custom_topic,
            script_preferences=series.script_preferences,
            language_code=language_code,
            num_scenes_min=scene_min,
            num_scenes_max=scene_max,
            episode_index=episode_index,
            total_episodes=total_episodes,
            previous_episode_summary=previous_episode_summary,
            series_title=_topic_from_series(series),
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
            episode_index=episode_index,
            total_episodes=total_episodes,
            previous_episode_summary=previous_episode_summary,
            series_title=_topic_from_series(series),
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
