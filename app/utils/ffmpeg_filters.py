"""
FFmpeg filter helpers. No heavy deps (only app.schemas.script_scenes).
Used by render task and testable without boto3/celery.
"""

from __future__ import annotations

from app.schemas.script_scenes import DEFAULT_ANIMATION, normalize_animation

FPS_OUT = 30


def zoompan_vf(duration: float, animation: dict | None) -> str:
    """Build zoompan filter from duration and optional animation spec (zoom_start, zoom_end, motion)."""
    num_frames = max(1, int(duration * FPS_OUT))
    anim = normalize_animation(animation) if animation else dict(DEFAULT_ANIMATION)
    zoom_start = anim.get("zoom_start", 1.0)
    zoom_end = anim.get("zoom_end", 1.2)
    motion = anim.get("motion", "ken_burns_zoom")
    if motion == "static":
        zoom_inc = 0.0
        zoom_expr = str(zoom_start)
    else:
        zoom_inc = (zoom_end - zoom_start) / num_frames if num_frames else 0.0002
        zoom_expr = f"min(zoom+{zoom_inc:.6f},{zoom_end})"
    base = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
    return base + f"zoompan=z='{zoom_expr}':d=1:s=1080x1920:fps={FPS_OUT}"
