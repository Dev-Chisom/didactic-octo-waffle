"""Celery app configuration."""

from celery import Celery
from app.config import get_settings

settings = get_settings()
celery_app = Celery(
    "auto_viral",
    broker=settings.celery_broker,
    backend=settings.redis_url,
    include=[
        "app.workers.tasks.script",
        "app.workers.tasks.media",
        "app.workers.tasks.render",
        "app.workers.tasks.post",
        "app.workers.tasks.schedule",
    ],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
