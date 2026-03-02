from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional, Tuple

from openai import OpenAI

from reel_engine.story import Shot, StoryPlan
from reel_engine.utils import read_env, sha1_hex


def synthesize_narration_from_story(
    plan: StoryPlan,
    *,
    model: str,
    voice: str,
    instructions: Optional[str],
    out_path: Path,
) -> Path:
    """
    Generate a single narration track for the whole reel using OpenAI TTS.

    We concatenate all shot narration lines into one script. This is cheap and
    good enough for crime/horror/cartoon reels where exact per-shot alignment
    isn't critical (images are B-roll under narration).
    """
    api_key = read_env("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Export it in your shell or .env before using "
            "--voice-provider openai."
        )

    text_parts: list[str] = []
    for shot in plan.shots:
        t = (shot.narration_text or "").strip()
        if t:
            text_parts.append(t)
    full_text = " ".join(text_parts).strip()
    if not full_text:
        raise ValueError("Story plan contains no narration text to send to TTS.")

    client = OpenAI(api_key=api_key)
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    kwargs = {
        "model": model,
        "voice": voice,
        "input": full_text,
        "response_format": "mp3",
    }
    if instructions:
        # Only supported on gpt-4o-mini-tts models, but harmless if ignored.
        kwargs["instructions"] = instructions

    with client.audio.speech.with_streaming_response.create(**kwargs) as response:
        response.stream_to_file(out_path)

    return out_path


def synthesize_narration_per_shot(
    plan: StoryPlan,
    *,
    model: str,
    voice: str,
    instructions: Optional[str],
    out_dir: Path,
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_bin: str = "ffprobe",
) -> Tuple[Path, StoryPlan]:
    """
    Generate TTS audio PER SHOT, then concatenate into one narration file.

    Why: This gives us near-perfect sync between captions (one per shot) and audio.

    Returns:
    - narration audio path (m4a)
    - a new StoryPlan with shot durations updated to match per-shot audio durations
    """
    api_key = read_env("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Export it in your shell or .env before using "
            "--voice-provider openai."
        )

    client = OpenAI(api_key=api_key)
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    segments_dir = out_dir / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)

    segment_paths: list[Path] = []
    segment_durations: list[float] = []

    for shot in plan.shots:
        text = (shot.narration_text or "").strip()
        if not text:
            # If empty, treat as short pause.
            segment_paths.append(_silence_segment(segments_dir / f"shot_{shot.id:02d}_silence.m4a", ffmpeg_bin))
            segment_durations.append(0.8)
            continue

        key = sha1_hex(f"{model}::{voice}::{instructions or ''}::{text}")
        seg_path = segments_dir / f"shot_{shot.id:02d}_{key}.mp3"
        if not seg_path.exists():
            kwargs = {
                "model": model,
                "voice": voice,
                "input": text,
                "response_format": "mp3",
            }
            if instructions:
                kwargs["instructions"] = instructions
            with client.audio.speech.with_streaming_response.create(**kwargs) as response:
                response.stream_to_file(seg_path)

        dur = _probe_duration_seconds(seg_path, ffprobe_bin=ffprobe_bin)
        # Clamp super-short clips so the hook isn't unreadable.
        dur = max(1.3, float(dur))
        segment_paths.append(seg_path)
        segment_durations.append(dur)

    # Concatenate audio segments into narration.m4a (AAC) for reliable joining.
    concat_list = out_dir / "audio_concat.txt"
    concat_list.write_text("".join([f"file '{p.as_posix()}'\n" for p in segment_paths]), encoding="utf-8")

    narration_path = out_dir / "narration.m4a"
    cmd = [
        ffmpeg_bin,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list),
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(narration_path),
    ]
    subprocess.run(cmd, check=True)

    # Build a new StoryPlan with durations updated to segment durations.
    new_shots: list[Shot] = []
    for shot, dur in zip(plan.shots, segment_durations):
        new_shots.append(
            Shot(
                id=shot.id,
                duration_sec=round(float(dur), 2),
                shot_type=shot.shot_type,
                emotion=shot.emotion,
                camera_motion=shot.camera_motion,
                narration_text=shot.narration_text,
                visual_beat=shot.visual_beat,
            )
        )
    new_duration = round(sum(s.duration_sec for s in new_shots), 2)
    new_plan = StoryPlan(style=plan.style, topic=plan.topic, duration_sec=new_duration, shots=new_shots)
    return narration_path, new_plan


def _probe_duration_seconds(path: Path, *, ffprobe_bin: str) -> float:
    cmd = [
        ffprobe_bin,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    out = subprocess.check_output(cmd).decode("utf-8").strip()
    try:
        return float(out)
    except ValueError:
        raise RuntimeError(f"Could not parse duration from ffprobe output: {out!r}")


def _silence_segment(out_path: Path, ffmpeg_bin: str) -> Path:
    # 0.8s of silence AAC to keep concat list consistent
    cmd = [
        ffmpeg_bin,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=24000:cl=mono",
        "-t",
        "0.80",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    return out_path

