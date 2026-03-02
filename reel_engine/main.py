from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from reel_engine.captions import build_caption_events, write_ass, burn_captions_into_frames
from reel_engine.config import default_config
from reel_engine.cost_model import estimate_cost
from reel_engine.image_gen import generate_images
from reel_engine.prompt_builder import build_image_prompts
from reel_engine.story import build_story_plan
from reel_engine.utils import ensure_dir, now_compact, write_json
from reel_engine.video_ffmpeg import RenderSettings, build_ffmpeg_command, pretty_cmd, run_ffmpeg
from reel_engine.music import pick_music_track
from reel_engine.voice_openai import synthesize_narration_per_shot, synthesize_narration_from_story


# Default SDXL model for Replicate.
# This version corresponds to stability-ai/sdxl.
DEFAULT_REPLICATE_SDXL_VERSION = "a00d0b7dcbb9c3fbb34ba87d2d5b46c56969c84a628bf778a7fdaec30b1b99c5"


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="reel_engine",
        description="Low-cost AI reel generator (images + FFmpeg motion/captions/music).",
    )
    p.add_argument("--style", default="crime", choices=["crime", "horror", "cartoon", "anime", "faceless"])
    p.add_argument("--topic", required=True, help="Topic/case hook used for prompts and seed locking.")
    p.add_argument(
        "--duration",
        type=float,
        default=45.0,
        help="Target duration per part in seconds (reels: 30–60; videos: 180–300 recommended).",
    )
    p.add_argument(
        "--parts",
        type=int,
        default=1,
        help="How many story parts to generate (each part renders its own MP4).",
    )

    p.add_argument(
        "--image-provider",
        default="replicate",
        choices=["local", "replicate", "pexels"],
        help="Image source: replicate (SDXL), local (files in assets/images), or pexels.",
    )
    p.add_argument("--replicate-model-version", default=DEFAULT_REPLICATE_SDXL_VERSION)

    # SDXL works well with ~720x1280 for vertical reels.
    p.add_argument("--width", type=int, default=720, help="Image generation width (9:16-ish).")
    p.add_argument("--height", type=int, default=1280, help="Image generation height (9:16-ish).")
    # SDXL prefers more steps than Lightning; keep moderate by default.
    p.add_argument("--steps", type=int, default=28)
    p.add_argument("--guidance-scale", type=float, default=7.5)

    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--crf", type=int, default=20)
    p.add_argument("--video-bitrate", default="4500k")
    p.add_argument("--music-volume", type=float, default=0.14)

    p.add_argument("--no-music", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="Build everything but do not run FFmpeg.")

    # Voiceover (OpenAI TTS)
    p.add_argument(
        "--voice-provider",
        default="none",
        choices=["none", "openai"],
        help="Text-to-speech provider for narration audio.",
    )
    p.add_argument(
        "--voice-model",
        default="gpt-4o-mini-tts",
        help="OpenAI TTS model name when using --voice-provider openai.",
    )
    p.add_argument(
        "--voice-name",
        default="auto",
        help="OpenAI TTS voice name (e.g. alloy, coral, nova). Use 'auto' to pick a style-appropriate default.",
    )

    p.add_argument(
        "--cost-per-image",
        type=float,
        default=None,
        help="Override cost per generated image (USD). Used for cost.json only.",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    repo_root = Path(__file__).resolve().parents[1]
    cfg = default_config(repo_root)

    parts = max(1, int(args.parts))
    run_id = f"{now_compact()}_{args.style}_{_slug(args.topic)[:24]}" + (f"_p{parts}" if parts > 1 else "")
    run_dir = ensure_dir(cfg.paths.runs_dir / run_id)
    manifest: dict = {
        "run_id": run_id,
        "style": args.style,
        "topic": args.topic,
        "parts_total": parts,
        "duration_per_part_requested_sec": float(args.duration),
        "parts": [],
    }

    for part_index in range(1, parts + 1):
        part_dir = ensure_dir(run_dir / f"part_{part_index:02d}")
        frames_dir = ensure_dir(part_dir / "frames")

        # 1) Story plan (per part); LLM narration cached by style+topic+shot_details
        plan = build_story_plan(
            style=args.style,
            topic=args.topic,
            duration_sec=float(args.duration),
            part_index=part_index,
            parts_total=parts,
            cache_dir=cfg.paths.repo_root / ".narration_cache",
        )

        # 2) Prompts + seed plan
        preset, base_seed, image_prompts = build_image_prompts(
            plan,
            width=int(args.width),
            height=int(args.height),
            steps=int(args.steps),
            guidance_scale=float(args.guidance_scale),
            part_index=part_index,
        )

        # 3) Narration (OpenAI TTS) – do this early so we can sync durations.
        narration_path: Optional[Path] = None
        if args.voice_provider == "openai":
            voice_name = args.voice_name
            if voice_name == "auto":
                voice_name = _auto_voice_for_style(args.style)
            narration_path, plan = synthesize_narration_per_shot(
                plan,
                model=args.voice_model,
                voice=voice_name,
                instructions=None,
                out_dir=part_dir / "audio",
                ffmpeg_bin=cfg.ffmpeg_binary,
                ffprobe_bin=cfg.ffprobe_binary,
            )

        # 4) Captions (ASS) + caption events
        captions_path = part_dir / "captions.ass"
        events = build_caption_events(plan)
        write_ass(
            events,
            out_path=str(captions_path),
            video_width=1080,
            video_height=1920,
        )

        # 5) Images (with caching)
        #
        # For --dry-run, generate placeholder frames so users can validate planning/output paths
        # without needing local images or paid providers.
        generated = []
        new_images = 0
        if args.dry_run:
            frame_paths = _write_placeholder_frames(
                frames_dir=frames_dir,
                num_frames=len(plan.shots),
                width=int(args.width),
                height=int(args.height),
            )
        else:
            generated, new_images = generate_images(
                image_prompts,
                provider=args.image_provider,
                style=args.style,
                run_frames_dir=frames_dir,
                global_cache_dir=cfg.paths.image_cache_dir,
                replicate_model_version=args.replicate_model_version,
            )
            frame_paths = [g.path for g in sorted(generated, key=lambda x: x.shot_id)]

        # Burn captions into frames (works even when FFmpeg lacks libass/drawtext).
        burn_captions_into_frames(
            events,
            frame_paths=[str(p) for p in frame_paths],
            font_dir=str(cfg.paths.fonts_dir),
        )

        # 6) Music (background under narration when enabled)
        music_path: Optional[Path] = None
        if not args.no_music:
            music_path = pick_music_track(music_root=cfg.paths.music_dir, style=args.style, seed=base_seed)

        # 7) FFmpeg render
        out_path = part_dir / "video.mp4"
        settings = RenderSettings(
            fps=int(args.fps),
            crf=int(args.crf),
            video_bitrate=str(args.video_bitrate),
            music_volume=float(args.music_volume),
            use_simple_concat=True,
        )
        cmd = build_ffmpeg_command(
            ffmpeg_bin=cfg.ffmpeg_binary,
            plan=plan,
            preset=preset,
            frame_paths=frame_paths,
            narration_path=narration_path,
            out_path=out_path,
            music_path=music_path,
            seed=base_seed,
            settings=settings,
        )

        # 8) Cost report + timeline (per part) — Replicate + narration LLM + OpenAI TTS
        cost_per_image = (
            float(args.cost_per_image)
            if args.cost_per_image is not None
            else cfg.pricing.sdxl_cost_per_image_usd
        )
        tts_chars = (
            sum(len((s.narration_text or "").strip()) for s in plan.shots)
            if args.voice_provider == "openai"
            else 0
        )
        cost = estimate_cost(
            images_new=new_images,
            cost_per_image_usd=cost_per_image,
            narration_llm_calls=1,
            cost_per_narration_call_usd=cfg.pricing.narration_llm_cost_per_call_usd,
            tts_chars=tts_chars,
            tts_cost_per_1m_chars_usd=cfg.pricing.openai_tts_cost_per_1m_chars_usd,
        )
        write_json(part_dir / "cost.json", cost)

        timeline = {
            "run_id": run_id,
            "part_index": part_index,
            "parts_total": parts,
            "style": args.style,
            "topic": args.topic,
            "duration_sec": plan.duration_sec,
            "base_seed": base_seed,
            "image_provider": args.image_provider,
            "image_params": {
                "width": args.width,
                "height": args.height,
                "steps": args.steps,
                "guidance_scale": args.guidance_scale,
            },
            "preset": preset.id,
            "music_path": str(music_path) if music_path else None,
            "captions_ass": str(captions_path),
            "narration_path": str(narration_path) if narration_path else None,
            "ffmpeg_cmd": pretty_cmd(cmd),
            "shots": [
                {
                    "id": s.id,
                    "duration_sec": s.duration_sec,
                    "shot_type": s.shot_type,
                    "emotion": s.emotion,
                    "camera_motion": s.camera_motion,
                    "visual_beat": s.visual_beat,
                    "narration_text": s.narration_text,
                    "image_prompt": next((p.prompt for p in image_prompts if p.shot_id == s.id), None),
                    "seed": next((p.seed for p in image_prompts if p.shot_id == s.id), None),
                    "frame_path": str(next((g.path for g in generated if g.shot_id == s.id), "")),
                    "cache_key": next((p.cache_key for p in image_prompts if p.shot_id == s.id), None),
                    "used_cache": next((g.used_cache for g in generated if g.shot_id == s.id), None),
                }
                for s in plan.shots
            ],
        }
        (part_dir / "timeline.json").write_text(json.dumps(timeline, indent=2, ensure_ascii=False) + "\n")

        manifest["parts"].append(
            {
                "part_index": part_index,
                "duration_sec": plan.duration_sec,
                "out_path": str(out_path),
                "timeline_path": str(part_dir / "timeline.json"),
                "cost_path": str(part_dir / "cost.json"),
            }
        )

        if args.dry_run:
            print(f"[dry-run] Would render part {part_index}/{parts} to: {out_path}")
            print(
                f"Cost (est.): ${cost.total_cost_usd:.4f} "
                f"(images={cost.images_cost_usd:.4f}, narration_llm={cost.narration_llm_cost_usd:.4f}, "
                f"tts={cost.tts_cost_usd:.4f})"
            )
            print(pretty_cmd(cmd))
        else:
            run_ffmpeg(cmd)
            print(f"Rendered part {part_index}/{parts}: {out_path}")
            print(
                f"Cost: ${cost.total_cost_usd:.4f} "
                f"(images={cost.images_cost_usd:.4f}, narration_llm={cost.narration_llm_cost_usd:.4f}, "
                f"tts={cost.tts_cost_usd:.4f})"
            )

    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return 0


def _write_placeholder_frames(*, frames_dir: Path, num_frames: int, width: int, height: int) -> list[Path]:
    """
    Create simple PNG frames for dry-run mode.
    """
    from PIL import Image

    frames: list[Path] = []
    frames_dir.mkdir(parents=True, exist_ok=True)
    w = int(width)
    h = int(height)
    for i in range(1, int(num_frames) + 1):
        out = (frames_dir / f"shot_{i:02d}.png").resolve()
        if not out.exists():
            im = Image.new("RGB", (w, h), color=(18, 18, 18))
            im.save(out, format="PNG", optimize=True)
        frames.append(out)
    return frames


def _slug(text: str) -> str:
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in {" ", "-", "_"}:
            out.append("_")
    s = "".join(out).strip("_")
    while "__" in s:
        s = s.replace("__", "_")
    return s or "topic"


def _auto_voice_for_style(style: str) -> str:
    """
    Pick a reasonable default OpenAI TTS voice per visual style.

    Users can always override via --voice-name.
    """
    key = style.strip().lower()
    if key == "cartoon":
        # Brighter, more energetic narrator for kids/cartoon content.
        return "nova"
    if key == "anime":
        # Slightly stylized, energetic but not too childish.
        return "nova"
    if key == "horror":
        # More neutral/deeper tone works better for tension.
        return "alloy"
    if key == "crime":
        return "alloy"
    # Faceless / fallback.
    return "alloy"


if __name__ == "__main__":
    raise SystemExit(main())

