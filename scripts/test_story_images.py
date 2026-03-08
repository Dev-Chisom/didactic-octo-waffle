#!/usr/bin/env python3
"""
Generate scene images for a story (no DB, no Celery).

Reads last_story_scenes.json (or a path you pass), calls the image service
(Replicate or Pexels per .env) and saves one PNG per scene.

Usage (from project root, e.g. cd /path/to/BE-auto-viral):
  python3 scripts/test_story_images.py
  python3 scripts/test_story_images.py path/to/scenes.json
  python3 scripts/test_story_images.py --out-dir scripts/out_images

Requirements:
  - .env with REPLICATE_API_TOKEN (or PEXELS_API_KEY for fallback)
  - Run test_story_generation.py first, or provide a scenes JSON with "visual_description" per scene
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.image_service import generate_scene_image


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate images for story scenes")
    parser.add_argument(
        "scenes_json",
        nargs="?",
        default=str(ROOT / "scripts" / "last_story_scenes.json"),
        help="Path to JSON array of scenes (each with visual_description)",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="Output directory for PNGs (default: scripts/out_images)",
    )
    args = parser.parse_args()

    scenes_path = Path(args.scenes_json)
    if not scenes_path.is_file():
        print(f"Scenes file not found: {scenes_path}")
        print("Run: python3 scripts/test_story_generation.py \"Your topic\"")
        return 1

    import json
    with open(scenes_path) as f:
        scenes = json.load(f)
    if not isinstance(scenes, list) or not scenes:
        print("Scenes JSON must be a non-empty array.")
        return 1

    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "scripts" / "out_images"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Images for {len(scenes)} scenes → {out_dir}")
    print()

    for i, scene in enumerate(scenes):
        vis = (scene.get("visual_description") or "").strip()
        if not vis:
            vis = (scene.get("image_prompt") or "cinematic atmospheric scene, no text").strip()
        num = i + 1
        out_path = out_dir / f"scene_{num:02d}.png"
        print(f"  Scene {num}: {vis[:55]}...")
        try:
            img_bytes = generate_scene_image(vis, scene_index=i)
            if img_bytes:
                out_path.write_bytes(img_bytes)
                print(f"    → {out_path}")
            else:
                print("    (no image – set REPLICATE_API_TOKEN or PEXELS_API_KEY in .env)")
        except Exception as e:
            print(f"    ERROR: {e}")
            return 1

    print()
    print("Done. Open folder to view: open", out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
