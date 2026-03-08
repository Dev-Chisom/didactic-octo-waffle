from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root is on sys.path so `app` imports work when running this
# script directly via `python3 scripts/test_avatar_generation.py`.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.base import SessionLocal
from app.db.models.episode import Episode
from app.db.models.series import Series
from app.workers.tasks.script import generate_script


def main() -> None:
    """
    Quick local test helper for the avatar pipeline.

    Usage:
        source .venv/bin/activate
        python3 scripts/test_avatar_generation.py

    Requirements:
        - At least one Series exists in the DB.
        - .env configured with:
            TTS_PROVIDER=elevenlabs
            ELEVENLABS_API_KEY=...
            REPLICATE_API_TOKEN=...
            REPLICATE_LIPSYNC_MODEL_VERSION=...
            ENABLE_AVATAR_MODE=true
        - Celery worker running:
            celery -A app.workers.celery_app.celery_app worker -l info
    """
    db = SessionLocal()
    try:
        series = db.query(Series).order_by(Series.created_at.asc()).first()
        if not series:
            print("No series found in database. Create a series via the UI first.")
            return

        # Pick next sequence number for this series.
        last_ep = (
            db.query(Episode)
            .filter(Episode.series_id == series.id)
            .order_by(Episode.sequence_number.desc())
            .first()
        )
        next_seq = (last_ep.sequence_number + 1) if last_ep else 1

        episode = Episode(
            id=uuid.uuid4(),
            series_id=series.id,
            sequence_number=next_seq,
            scheduled_at=datetime.now(timezone.utc),
            status="scheduled",
        )
        db.add(episode)
        db.commit()
        db.refresh(episode)

        print(f"Created test episode {episode.id} for series {series.id} (sequence {next_seq}).")

        # Enqueue the script-generation task; this will chain into generate_avatar_video
        # when ENABLE_AVATAR_MODE=true.
        async_result = generate_script.delay(str(episode.id))
        print(f"Enqueued generate_script task with id={async_result.id}.")
        print("Watch your Celery worker logs for avatar generation and lip-sync rendering.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

