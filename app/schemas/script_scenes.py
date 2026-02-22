from __future__ import annotations

from typing import Any, TypedDict


class SceneSpec(TypedDict, total=False):
    scene: int
    text: str
    visual_description: str


class MediaSceneRef(TypedDict):
    image_asset_id: str
    voice_asset_id: str
    duration_seconds: float


def validate_scenes(raw: Any) -> list[SceneSpec]:
    if not isinstance(raw, list) or len(raw) == 0:
        raise ValueError("scenes must be a non-empty list")
    out: list[SceneSpec] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"scene {i} must be an object")
        text = (item.get("text") or "").strip()
        if not text:
            raise ValueError(f"scene {i} missing 'text'")
        vis = (item.get("visual_description") or "").strip() or text[:500]
        out.append({
            "scene": int(item.get("scene", i + 1)),
            "text": text,
            "visual_description": vis,
        })
    return out
