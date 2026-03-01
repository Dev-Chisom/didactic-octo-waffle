import uuid

from app.db.base import SessionLocal
from app.db.models.episode import Episode
from app.services.generation_service import run_script_generation
from app.workers.celery_app import celery_app


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def generate_script(self, episode_id: str):
    db = SessionLocal()
    episode = None
    try:
        episode = db.query(Episode).filter(Episode.id == uuid.UUID(episode_id)).first()
        if not episode:
            raise ValueError(f"Episode {episode_id} not found")

        result = run_script_generation(db, episode.id)
        db.refresh(episode)
        # Chain media generation so video is ready before scheduled_at
        from app.workers.tasks.media import generate_media

        generate_media.delay(episode_id)
        return {
            "episode_id": episode_id,
            "script_id": result.get("script_id"),
            "status": "completed",
            "script_length": result.get("script_length"),
            "scene_count": result.get("scene_count"),
        }
    except Exception as e:
        if episode:
            episode.status = "failed"
            episode.error = {"step": "script_generation", "message": str(e)}
            db.commit()
        raise
    finally:
        db.close()
