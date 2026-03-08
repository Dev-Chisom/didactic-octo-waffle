from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class LipSyncError(RuntimeError):
    """Raised when the Replicate lip-sync job fails or times out."""


async def run_lipsync(
    face_image_url: str,
    audio_url: str,
    timeout_seconds: int = 600,
    poll_interval_seconds: float = 3.0,
) -> str:
    """
    Call the Replicate lip-sync model and return the output video URL.

    Uses input keys expected by sync/lipsync-2-pro: "video" (face/image URL) and "audio".
    - Creates a prediction via Replicate's /v1/predictions endpoint
    - Polls until status == 'succeeded' or 'failed' or timeout (status-aware; Lip-sync is GPU-heavy and slow)
    - Returns the final output URL (str)

    Note: This blocks for the full prediction. For high throughput, consider splitting into
    two Celery tasks: one that starts the prediction and one that polls later.
    """
    settings = get_settings()
    api_token = settings.replicate_api_token
    model_version = settings.replicate_lipsync_model_version
    if not api_token:
        raise ValueError("REPLICATE_API_TOKEN is not configured")
    if not model_version:
        raise ValueError("REPLICATE_LIPSYNC_MODEL_VERSION is not configured")
    if not face_image_url or not audio_url:
        raise ValueError("face_image_url and audio_url are required")

    headers = {
        "Authorization": f"Token {api_token}",
        "Content-Type": "application/json",
    }
    # sync/lipsync-2-pro (and many Replicate lip-sync models) expect "video" + "audio".
    # "video" can be an image URL (model treats it as a single frame).
    payload: dict[str, Any] = {
        "version": model_version,
        "input": {
            "video": face_image_url,
            "audio": audio_url,
        },
    }

    # Create prediction (short-lived client).
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.replicate.com/v1/predictions",
            headers=headers,
            json=payload,
        )
    if resp.status_code == 422:
        try:
            err_body = resp.json()
        except Exception:
            err_body = resp.text or "(non-JSON response)"
        logger.error(
            "Replicate lip-sync 422 Unprocessable Entity. Response: %s. "
            "Ensure REPLICATE_LIPSYNC_MODEL_VERSION and input keys (video, audio) match your model.",
            err_body,
        )
    resp.raise_for_status()
    data = resp.json()
    prediction_id = data.get("id")
    status = data.get("status")
    if not prediction_id:
        raise LipSyncError("Replicate did not return a prediction id")

    started_at = time.monotonic()
    last_error: str | None = None

    # Poll until terminal state or timeout.
    while status in {"starting", "processing", "queued"}:
        if time.monotonic() - started_at > timeout_seconds:
            logger.warning(
                "Lip-sync timeout after %ds; prediction_id=%s last_status=%s",
                timeout_seconds,
                prediction_id,
                status,
            )
            raise LipSyncError(
                f"Lip-sync prediction timed out after {timeout_seconds} seconds "
                f"(prediction_id={prediction_id}, last_status={status!r}). "
                "Check https://replicate.com/predictions or increase REPLICATE_LIPSYNC_TIMEOUT_SECONDS."
            )

        await asyncio.sleep(poll_interval_seconds)

        # Use a fresh client per poll to avoid stale connections over long runtimes.
        try:
            async with httpx.AsyncClient(timeout=30.0) as poll_client:
                poll_resp = await poll_client.get(
                    f"https://api.replicate.com/v1/predictions/{prediction_id}",
                    headers=headers,
                )
                poll_resp.raise_for_status()
                data = poll_resp.json()
                status = data.get("status")
                last_error = (data.get("error") or "") or last_error
        except httpx.RequestError as e:
            # Treat transient read/connection errors as soft failures and keep polling until timeout.
            logger.warning(
                "Replicate lip-sync poll transient error for prediction_id=%s: %s (will retry until timeout).",
                prediction_id,
                e,
            )

        if status != "succeeded":
            raise LipSyncError(f"Lip-sync prediction failed with status={status!r}, error={last_error!r}")

        output = data.get("output")
        # Replicate models often return either a single URL or a list of URLs.
        video_url: str | None = None
        if isinstance(output, str):
            video_url = output
        elif isinstance(output, list):
            # Prefer the last entry if multiple URLs are present.
            for item in reversed(output):
                if isinstance(item, str):
                    video_url = item
                    break

        if not video_url:
            raise LipSyncError("Replicate prediction succeeded but no output video URL was found")
        return video_url


def run_lipsync_sync(
    face_image_url: str,
    audio_url: str,
    timeout_seconds: int = 600,
    poll_interval_seconds: float = 3.0,
) -> str:
    """
    Synchronous wrapper for Celery tasks or other sync callers.
    """

    return asyncio.run(
        run_lipsync(
            face_image_url=face_image_url,
            audio_url=audio_url,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )
    )

