from __future__ import annotations

from typing import Any, Literal, TypedDict

# ---------------------------------------------------------------------------
# Animation (FFmpeg camera motion)
# ---------------------------------------------------------------------------

MotionType = Literal[
    "ken_burns_zoom",
    "ken_burns_pan_left",
    "ken_burns_pan_right",
    "zoom_in",
    "zoom_out",
    "static",
]


class AnimationSpec(TypedDict, total=False):
    """Camera motion for background; used by render task for FFmpeg zoompan."""

    motion: MotionType
    zoom_start: float
    zoom_end: float
    pan_x_start: float
    pan_x_end: float
    pan_y_start: float
    pan_y_end: float


# ---------------------------------------------------------------------------
# Scene (LLM output → script.scenes)
# ---------------------------------------------------------------------------

SceneType = Literal["narration", "dialogue"]


class SceneSpec(TypedDict, total=False):
    """Single scene: narration or dialogue, with image prompt and animation hint."""

    scene: int
    text: str
    visual_description: str
    scene_type: SceneType
    duration_seconds: float
    character_id: str
    image_prompt: str
    animation: AnimationSpec
    metadata: dict[str, Any]


# ---------------------------------------------------------------------------
# Media scene ref (after asset generation → episode.error["media"]["scenes"])
# ---------------------------------------------------------------------------


class MediaSceneRef(TypedDict, total=False):
    """Per-scene assets for render: image, voice, optional lip-sync, duration, animation."""

    image_asset_id: str
    voice_asset_id: str
    duration_seconds: float
    lipsync_asset_id: str
    character_id: str
    animation: AnimationSpec


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

DEFAULT_ANIMATION: AnimationSpec = {"motion": "ken_burns_zoom", "zoom_start": 1.0, "zoom_end": 1.2}


def normalize_animation(raw: Any) -> AnimationSpec:
    """Build AnimationSpec from scene.animation; fill defaults."""
    if not raw or not isinstance(raw, dict):
        return dict(DEFAULT_ANIMATION)
    motion = raw.get("motion") or "ken_burns_zoom"
    if motion not in ("ken_burns_zoom", "ken_burns_pan_left", "ken_burns_pan_right", "zoom_in", "zoom_out", "static"):
        motion = "ken_burns_zoom"
    return {
        "motion": motion,
        "zoom_start": float(raw.get("zoom_start", 1.0)),
        "zoom_end": float(raw.get("zoom_end", 1.2)),
        "pan_x_start": float(raw.get("pan_x_start", 0)),
        "pan_x_end": float(raw.get("pan_x_end", 0)),
        "pan_y_start": float(raw.get("pan_y_start", 0)),
        "pan_y_end": float(raw.get("pan_y_end", 0)),
    }


def validate_scenes(raw: Any) -> list[SceneSpec]:
    """Validate and normalize script.scenes; supports long-form schema (scene_type, animation, etc.)."""
    if not isinstance(raw, list) or len(raw) == 0:
        raise ValueError("scenes must be a non-empty list")
    out: list[SceneSpec] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"scene {i} must be an object")
        text = (item.get("text") or "").strip()
        if not text:
            raise ValueError(f"scene {i} missing 'text'")
        vis = (item.get("visual_description") or "").strip() or (item.get("image_prompt") or "").strip() or text[:500]
        scene_type: SceneType = (item.get("scene_type") or "narration").lower()
        if scene_type not in ("narration", "dialogue"):
            scene_type = "narration"
        if scene_type == "dialogue" and not (item.get("character_id") or "").strip():
            raise ValueError(f"scene {i} has scene_type 'dialogue' but missing 'character_id'")
        duration = item.get("duration_seconds")
        if duration is not None:
            try:
                duration = float(duration)
                duration = max(0.5, min(60.0, duration))
            except (TypeError, ValueError):
                duration = None
        spec: SceneSpec = {
            "scene": int(item.get("scene", i + 1)),
            "text": text,
            "visual_description": vis,
            "scene_type": scene_type,
        }
        if duration is not None:
            spec["duration_seconds"] = duration
        if (item.get("character_id") or "").strip():
            spec["character_id"] = (item.get("character_id") or "").strip()
        if (item.get("image_prompt") or "").strip():
            spec["image_prompt"] = (item.get("image_prompt") or "").strip()
        if item.get("animation") and isinstance(item["animation"], dict):
            spec["animation"] = normalize_animation(item["animation"])
        if isinstance(item.get("metadata"), dict):
            spec["metadata"] = item["metadata"]
        out.append(spec)
    return out


# ---------------------------------------------------------------------------
# Procedural storytelling: dialogue expansion → SceneSpec[]
# ---------------------------------------------------------------------------

def dialogue_expansion_to_scenes(
    expanded: list[dict[str, Any]],
    image_prompt_key: str = "image_prompt",
    use_dialogue_scenes: bool = True,
) -> list[SceneSpec]:
    """
    Map procedural dialogue expansion output to SceneSpec for the video pipeline.

    Each expanded item has: scene_number, narration, dialogue[] (character_id, line).
    - If use_dialogue_scenes: one narration scene + one scene per dialogue line (for lip-sync).
    - If not: one scene per expanded item with text = narration + " " + all lines (no per-line lip-sync).
    visual_description is taken from the scene seed's image_prompt (pass per-scene or use a default).
    """
    out: list[SceneSpec] = []
    scene_index = 1
    for item in expanded:
        narration = (item.get("narration") or "").strip()
        dialogue_list = item.get("dialogue") or []
        if not isinstance(dialogue_list, list):
            dialogue_list = []
        visual = (item.get(image_prompt_key) or item.get("visual_description") or "").strip() or "cinematic scene, no text"
        base_meta: dict[str, Any] = {}
        if item.get("scene_number") is not None:
            base_meta["scene_number"] = item["scene_number"]
        if item.get("emotion"):
            base_meta["emotion"] = item["emotion"]

        if use_dialogue_scenes and dialogue_list:
            if narration:
                out.append({
                    "scene": scene_index,
                    "text": narration,
                    "visual_description": visual,
                    "scene_type": "narration",
                    "animation": dict(DEFAULT_ANIMATION),
                    "metadata": {**base_meta, "beat": "narration"},
                })
                scene_index += 1
            for d in dialogue_list:
                if not isinstance(d, dict):
                    continue
                line = (d.get("line") or "").strip()
                if not line:
                    continue
                cid = (d.get("character_id") or d.get("character") or "").strip().lower().replace(" ", "_")
                out.append({
                    "scene": scene_index,
                    "text": line,
                    "visual_description": visual,
                    "scene_type": "dialogue",
                    "character_id": cid or "unknown",
                    "animation": dict(DEFAULT_ANIMATION),
                    "metadata": {**base_meta, "emotion": d.get("emotion"), "beat": "dialogue"},
                })
                scene_index += 1
        else:
            parts = [narration] if narration else []
            for d in dialogue_list:
                if isinstance(d, dict) and (d.get("line") or "").strip():
                    parts.append((d.get("line") or "").strip())
            text = " ".join(parts).strip()
            if not text:
                continue
            out.append({
                "scene": scene_index,
                "text": text,
                "visual_description": visual,
                "scene_type": "narration",
                "animation": dict(DEFAULT_ANIMATION),
                "metadata": base_meta,
            })
            scene_index += 1
    return out
