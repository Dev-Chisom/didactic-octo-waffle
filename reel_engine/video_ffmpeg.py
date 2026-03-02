from __future__ import annotations

import random
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from reel_engine.story import StoryPlan
from reel_engine.style_presets import StylePreset


@dataclass(frozen=True)
class RenderSettings:
    width: int = 1080
    height: int = 1920
    fps: int = 30
    video_bitrate: str = "4500k"
    audio_bitrate: str = "160k"
    crf: int = 20

    # How much extra resolution to render before zoom/pan (for motion room).
    motion_overscale: float = 1.08

    # Background music loudness (0.0–1.0).
    music_volume: float = 0.14

    # When True, use a simpler FFmpeg filter graph (no zoompan) that just
    # scales each still and concatenates the clips. Helpful for debugging
    # “stuck on one image” issues.
    use_simple_concat: bool = False


def build_ffmpeg_command(
    *,
    ffmpeg_bin: str,
    plan: StoryPlan,
    preset: StylePreset,
    frame_paths: list[Path],
    narration_path: Optional[Path],
    out_path: Path,
    music_path: Optional[Path],
    seed: int,
    settings: RenderSettings,
) -> list[str]:
    if len(frame_paths) != len(plan.shots):
        raise ValueError("frame_paths must match number of shots")

    total_duration = sum(float(s.duration_sec) for s in plan.shots)
    args: list[str] = [ffmpeg_bin, "-y", "-hide_banner"]

    # Inputs: loop each still image for its shot duration.
    for shot, img in zip(plan.shots, frame_paths):
        args += [
            "-loop",
            "1",
            "-t",
            f"{float(shot.duration_sec):.2f}",
            "-i",
            str(img),
        ]

    # Optional audio inputs.
    narration_index: Optional[int] = None
    music_index: Optional[int] = None
    if narration_path is not None:
        narration_index = len(frame_paths)
        args += ["-i", str(narration_path)]
    if music_path is not None:
        music_index = len(frame_paths) if narration_index is None else len(frame_paths) + 1
        # Loop music to cover full duration (we will trim/mix later).
        args += ["-stream_loop", "-1", "-i", str(music_path)]

    filter_complex, vout_label = _build_filter_complex(
        plan=plan,
        preset=preset,
        seed=seed,
        settings=settings,
        num_video_inputs=len(frame_paths),
        music_input_index=None,
        total_duration=total_duration,
    )
    # When both narration and music are present, mix them into a single audio stream.
    if narration_index is not None and music_index is not None:
        filter_complex = (
            f"{filter_complex};"
            f"[{narration_index}:a][{music_index}:a]"
            f"amix=inputs=2:duration=first:dropout_transition=2,"
            f"volume=1[aout]"
        )
        args += ["-filter_complex", filter_complex, "-map", f"[{vout_label}]", "-map", "[aout]"]
        args += ["-c:a", "aac", "-b:a", settings.audio_bitrate]
        # Cut to narration length (amix duration=first).
        args += ["-shortest"]
    else:
        args += ["-filter_complex", filter_complex, "-map", f"[{vout_label}]"]

        if narration_index is not None:
            # Narration only.
            args += ["-map", f"{narration_index}:a", "-shortest"]
            args += ["-c:a", "aac", "-b:a", settings.audio_bitrate]
        elif music_index is not None:
            # Background music only – looped to cover full duration; trim explicitly to the video length.
            args += ["-map", f"{music_index}:a"]
            args += ["-af", f"volume={settings.music_volume}"]
            args += ["-c:a", "aac", "-b:a", settings.audio_bitrate]
            args += ["-t", f"{total_duration:.3f}"]
        else:
            args += ["-an"]

    # Output encoding tuned for TikTok/IG.
    args += [
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-level",
        "4.1",
        "-r",
        str(settings.fps),
        "-b:v",
        settings.video_bitrate,
        "-crf",
        str(settings.crf),
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    return args


def run_ffmpeg(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def pretty_cmd(cmd: list[str]) -> str:
    return " ".join(shlex.quote(c) for c in cmd)


def _build_filter_complex(
    *,
    plan: StoryPlan,
    preset: StylePreset,
    seed: int,
    settings: RenderSettings,
    num_video_inputs: int,
    music_input_index: Optional[int],
    total_duration: float,
) -> tuple[str, str]:
    fps = int(settings.fps)
    w = int(settings.width)
    h = int(settings.height)
    overscale = float(settings.motion_overscale)

    rng = random.Random(seed)

    parts: list[str] = []
    clip_labels: list[str] = []

    for i, shot in enumerate(plan.shots):
        frames = max(2, int(round(float(shot.duration_sec) * fps)))
        src = f"[{i}:v]"
        out = f"v{i}"

        # Optional: extremely simple path – just scale & center-crop each still
        # and skip zoompan. This is more robust across FFmpeg builds.
        if getattr(settings, "use_simple_concat", False):
            parts.append(
                f"{src}"
                f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},"
                "format=yuv420p"
                f"[{out}]"
            )
            clip_labels.append(f"[{out}]")
            continue

        # Default path: add lightweight zoom/pan motion.
        motion = shot.camera_motion.strip().lower()
        if motion in {"slow_push_in", "gentle_zoom"}:
            direction = rng.choice(["center", "up", "down", "left", "right"])
            z_expr, x_expr, y_expr = _zoompan_expr(direction=direction)
        elif motion in {"subtle_pan"}:
            direction = rng.choice(["left", "right", "up", "down"])
            z_expr, x_expr, y_expr = _zoompan_expr(direction=direction, pan_only=True)
        else:
            z_expr, x_expr, y_expr = _zoompan_expr(direction="center", static=True)

        sw = int(round(w * overscale))
        sh = int(round(h * overscale))

        # scale -> normalize exposure per clip -> zoompan -> format
        parts.append(
            f"{src}"
            f"scale={sw}:{sh}:force_original_aspect_ratio=increase,"
            f"crop={sw}:{sh},"
            "normalize,"
            f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={frames}:s={w}x{h}:fps={fps},"
            "format=yuv420p"
            f"[{out}]"
        )
        clip_labels.append(f"[{out}]")

    # Concat all clips.
    vcat = "vcat"
    parts.append("".join(clip_labels) + f"concat=n={num_video_inputs}:v=1:a=0[{vcat}]")

    # Style grade + grain/shake.
    vgraded = "vgraded"
    grade_chain = _style_video_chain(preset=preset, seed=seed, fps=fps)
    parts.append(f"[{vcat}]{grade_chain}[{vgraded}]")

    # Captions are burned into frames pre-render (Pillow), because this FFmpeg build
    # may not include libass/drawtext filters.
    return ";".join(parts), vgraded


def _style_video_chain(*, preset: StylePreset, seed: int, fps: int) -> str:
    # Keep this very lightweight: eq + grain + optional vignette + optional jitter.
    chain: list[str] = []
    chain.append(
        f"eq=saturation={preset.eq_saturation}:contrast={preset.eq_contrast}:brightness={preset.eq_brightness}"
    )

    if preset.grain_strength > 0:
        # FFmpeg noise uses integer-ish strengths; we map to a reasonable range.
        strength = int(round(preset.grain_strength * 50))
        strength = max(1, min(20, strength))
        # allf=t gives temporal grain that drifts over time instead of full white-noise every frame.
        chain.append(f"noise=alls={strength}:allf=t")

    if preset.vignette:
        chain.append("vignette=PI/7")

    if preset.shake:
        # Subtle, organic camera jitter: randomize phase, slightly different axes, and clamp to padded area.
        rng = random.Random(seed + 42)
        freq = 1 + (seed % 3)
        amp = 1  # pixels; keep this very low for TikTok-style content
        margin = 4  # keep crop safely within padded bounds
        phase_x = rng.random() * 6.283  # ~2*PI
        phase_y = rng.random() * 6.283
        x_expr = (
            f"clip({margin}+{amp}*sin(2*PI*{freq}*t+{phase_x:.3f}),0,{2*margin})"
        )
        y_expr = (
            f"clip({margin}+{amp}*cos(2*PI*{freq*1.3:.2f}*t+{phase_y:.3f}),0,{2*margin})"
        )
        # `translate` filter isn't available in some FFmpeg builds; emulate it with pad+crop.
        chain.append(
            f"pad=iw+{2 * margin}:ih+{2 * margin}:{margin}:{margin}:color=black"
        )
        chain.append(
            "crop="
            f"iw-{2 * margin}:ih-{2 * margin}:"
            f"x='{x_expr}':"
            f"y='{y_expr}'"
        )

    return ",".join(chain)


def _zoompan_expr(*, direction: str, pan_only: bool = False, static: bool = False) -> tuple[str, str, str]:
    # zoompan expressions (quoted in filter_complex):
    #
    # - zoom increases slightly each frame to simulate push-in
    # - x/y define top-left of crop window, so we offset to bias the movement direction
    #
    # zoompan uses:
    # - zoom: current zoom factor
    # - iw/ih: input width/height
    if static:
        z = "1.0"
    elif pan_only:
        # Keep zoom at 1.0 and animate only x/y.
        z = "1.0"
    else:
        # Gentle push-in over the clip.
        z = "min(zoom+0.0010,1.08)"

    # Base centered crop.
    x_center = "iw/2-(iw/zoom/2)"
    y_center = "ih/2-(ih/zoom/2)"

    # No directional bias – just a centered push-in.
    if direction == "center":
        return z, x_center, y_center

    # Directional pans: use the output frame index `on` so motion is smooth over time.
    if direction == "left":
        return z, f"iw/2-(iw/zoom/2)-on*0.4", y_center
    if direction == "right":
        return z, f"iw/2-(iw/zoom/2)+on*0.4", y_center
    if direction == "up":
        return z, x_center, f"ih/2-(ih/zoom/2)-on*0.3"
    if direction == "down":
        return z, x_center, f"ih/2-(ih/zoom/2)+on*0.3"

    return z, x_center, y_center

