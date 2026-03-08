import asyncio
from typing import Any

import httpx
import pytest

from app.services.lipsync import LipSyncError, run_lipsync


class DummyResponse:
    def __init__(self, json_data: dict[str, Any], status_code: int = 200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if not (200 <= self.status_code < 300):
            raise httpx.HTTPStatusError("error", request=None, response=None)  # type: ignore[arg-type]

    def json(self) -> dict[str, Any]:
        return self._json


@pytest.mark.asyncio
async def test_run_lipsync_times_out(monkeypatch):
    """run_lipsync should raise LipSyncError on timeout."""

    async def fake_post(*args, **kwargs) -> DummyResponse:  # type: ignore[override]
        return DummyResponse({"id": "pred_123", "status": "processing"})

    async def fake_get(*args, **kwargs) -> DummyResponse:  # type: ignore[override]
        return DummyResponse({"id": "pred_123", "status": "processing"})

    class DummyClient:
        def __init__(self, *a: Any, **kw: Any) -> None:
            pass

        async def __aenter__(self) -> "DummyClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
            return None

        post = fake_post
        get = fake_get

    monkeypatch.setattr("app.services.lipsync.httpx.AsyncClient", DummyClient)

    # Use a very small timeout to force the timeout path.
    with pytest.raises(LipSyncError):
        await run_lipsync(
            face_image_url="https://example.com/avatar.png",
            audio_url="https://example.com/audio.wav",
            timeout_seconds=0,
            poll_interval_seconds=0,
        )


def test_celery_task_has_expected_retries():
    """Basic sanity check that avatar task is configured with the desired retry policy."""
    from app.workers.tasks.avatar import generate_avatar_video

    assert generate_avatar_video.max_retries == 3

