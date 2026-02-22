"""Post to platform APIs: upload video, set post.status and platform_post_id."""

import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.db.models.post import Post
from app.db.models.episode import Episode
from app.db.models.asset import Asset
from app.db.models.social_account import SocialAccount
from app.services.platform_publish import publish_to_platform
from app.workers.celery_app import celery_app


@celery_app.task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def post_to_platform(self, post_id: str):
    """Load post, episode, video asset, and social account; call platform upload API; set post.status and platform_post_id."""
    db: Session = SessionLocal()
    try:
        post = db.query(Post).filter(Post.id == uuid.UUID(post_id)).first()
        if not post:
            raise ValueError(f"Post {post_id} not found")

        post.status = "posting"
        db.commit()

        episode = db.query(Episode).filter(Episode.id == post.episode_id).first()
        if not episode:
            post.status = "failed"
            post.error = {"message": "Episode not found"}
            db.commit()
            return {"post_id": post_id, "status": "failed"}

        video_asset_id = episode.video_asset_id
        if not video_asset_id:
            post.status = "failed"
            post.error = {"message": "Episode has no video; run render first"}
            db.commit()
            return {"post_id": post_id, "status": "failed"}

        video_asset = db.query(Asset).filter(Asset.id == video_asset_id).first()
        if not video_asset:
            post.status = "failed"
            post.error = {"message": "Video asset not found"}
            db.commit()
            return {"post_id": post_id, "status": "failed"}

        social_account = db.query(SocialAccount).filter(SocialAccount.id == post.social_account_id).first()
        if not social_account:
            post.status = "failed"
            post.error = {"message": "Social account not found"}
            db.commit()
            return {"post_id": post_id, "status": "failed"}

        caption = episode.script.text if episode.script else ""

        status, platform_post_id, err = publish_to_platform(
            db, social_account, video_asset, caption, post_id
        )

        if status == "posted":
            post.status = "posted"
            post.platform_post_id = platform_post_id
            post.posted_at = datetime.now(timezone.utc)
            post.error = None
        else:
            post.status = "failed"
            post.error = err

        db.commit()
        return {"post_id": post_id, "status": post.status, "platform_post_id": platform_post_id}
    finally:
        db.close()
