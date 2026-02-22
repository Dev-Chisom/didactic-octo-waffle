"""OAuth state storage in Redis for social connect callbacks."""

import json
from typing import Any, Optional

import redis

from app.config import get_settings

STATE_TTL_SECONDS = 600  # 10 minutes
STATE_PREFIX = "oauth_state:"


def _client() -> redis.Redis:
    settings = get_settings()
    return redis.from_url(settings.redis_url, decode_responses=True)


def set_oauth_state(state: str, workspace_id: str, platform: str) -> None:
    """Store state -> {workspace_id, platform} in Redis."""
    client = _client()
    key = f"{STATE_PREFIX}{state}"
    value = json.dumps({"workspace_id": str(workspace_id), "platform": platform})
    client.setex(key, STATE_TTL_SECONDS, value)


def get_oauth_state(state: str) -> Optional[dict[str, Any]]:
    """Retrieve and delete state; return {workspace_id, platform} or None."""
    client = _client()
    key = f"{STATE_PREFIX}{state}"
    value = client.get(key)
    if value is None:
        return None
    client.delete(key)
    data = json.loads(value)
    return data
