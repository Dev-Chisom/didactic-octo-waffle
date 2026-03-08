#!/usr/bin/env python3
"""
Generate a ~2-minute story via OpenAI and print it (no DB, no video).

Usage (from project root, e.g. cd /path/to/BE-auto-viral):
  python3 scripts/test_story_generation.py
  python3 scripts/test_story_generation.py "The last library on the moon"
  python3 scripts/test_story_generation.py "Jungle temple curse" horror

Requirements:
  - .env with OPENAI_API_KEY set
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.llm_service import generate_script_scenes


def main() -> None:
    topic = "A stranger arrives at a small village with a secret"
    content_type = "custom"
    if len(sys.argv) >= 2:
        topic = sys.argv[1].strip()
    if len(sys.argv) >= 3:
        content_type = sys.argv[2].strip().lower()

    custom_topic = {"topicTitle": topic}
    script_preferences = {
        "storyLength": "2_min",
    }

    print("Calling OpenAI for ~2-minute story...")
    print(f"  Topic: {topic}")
    print(f"  Content type: {content_type}")
    print()

    scenes = generate_script_scenes(
        content_type=content_type,
        custom_topic=custom_topic,
        script_preferences=script_preferences,
        language_code="en-US",
        num_scenes_min=8,
        num_scenes_max=12,
        episode_index=1,
        total_episodes=1,
        previous_episode_summary=None,
        series_title=topic,
    )

    full_text = "\n\n".join((s.get("text") or "").strip() for s in scenes)
    word_count = len(full_text.split())
    print(f"Generated {len(scenes)} scenes (~{word_count} words, ~2 min when spoken)")
    print()
    print("=" * 60)
    print("STORY (full text)")
    print("=" * 60)
    print(full_text)
    print()
    print("=" * 60)
    print("SCENES (for video pipeline)")
    print("=" * 60)
    for s in scenes:
        idx = s.get("scene", 0)
        text = (s.get("text") or "")[:80]
        vis = (s.get("visual_description") or "")[:60]
        print(f"  Scene {idx}: {text}...")
        print(f"    Visual: {vis}...")
        print()

    out_path = ROOT / "scripts" / "last_story_scenes.json"
    with open(out_path, "w") as f:
        json.dump(scenes, f, indent=2)
    print(f"Scenes saved to {out_path}")
    print("Done.")


if __name__ == "__main__":
    main()
