#!/usr/bin/env python3
"""
Generate TTS audio for each scene of a story (no DB, no Celery).

Uses last_story_scenes.json by default, or a path you pass. Calls the TTS
service (OpenAI or ElevenLabs per .env) and saves one MP3 per scene.

Usage (from project root, e.g. cd /path/to/BE-auto-viral):
  python3 scripts/test_story_tts.py
  python3 scripts/test_story_tts.py path/to/scenes.json
  python3 scripts/test_story_tts.py path/to/scenes.json --voice nova
  python3 scripts/test_story_tts.py --play              # generate then play in order
  python3 scripts/test_story_tts.py --play --voice nova  # generate with voice then play
  python3 scripts/test_story_tts.py --play-only         # play already-generated MP3s only (no API)
  python3 scripts/test_story_tts.py --character-voices hero:nova,villain:onyx   # dialogue scenes use different voices

Requirements:
  - .env with OPENAI_API_KEY (and ELEVENLABS_* if TTS_PROVIDER=elevenlabs)
  - Run test_story_generation.py first, or provide a scenes JSON with "text" per scene

Note: last_story_scenes.json from test_story_generation.py is narration-only (one voice).
For dialogue with different voices, use scenes that have "scene_type": "dialogue" and
"character_id" per scene, and pass --character-voices (e.g. hero:nova,villain:onyx).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.tts_service import synthesize
from app.workers.tasks.media import _voice_id_for_scene


def _play_audio(path: Path) -> bool:
    """Play one MP3; return True if a player was used."""
    path = path.resolve()
    if not path.is_file():
        return False
    # macOS
    try:
        subprocess.run(["afplay", str(path)], check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    # ffplay (ffmpeg)
    try:
        subprocess.run(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)],
            check=True,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass
    return False


def play_story(out_dir: Path) -> None:
    """Play scene_01.mp3, scene_02.mp3, ... in order (any that exist)."""
    mp3s = sorted(out_dir.glob("scene_*.mp3"))
    if not mp3s:
        print(f"No scene_*.mp3 in {out_dir}. Generate first (run without --play).")
        return
    played = 0
    for mp3 in mp3s:
        print(f"  Playing {mp3.name}...")
        if _play_audio(mp3):
            played += 1
        else:
            print("  No player (afplay/ffplay). Open manually: open", out_dir)
            break
    if played:
        print("Done listening.")
    else:
        print(f"Open the folder to play: open {out_dir}")
        print("  or: ffplay scripts/out_tts/scene_01.mp3")


def main() -> None:
    parser = argparse.ArgumentParser(description="TTS for story scenes")
    parser.add_argument(
        "scenes_json",
        nargs="?",
        default=str(ROOT / "scripts" / "last_story_scenes.json"),
        help="Path to JSON array of scenes (each with 'text')",
    )
    parser.add_argument("--voice", default="alloy", help="Narrator voice (e.g. alloy, nova, or ElevenLabs ID)")
    parser.add_argument(
        "--character-voices",
        default="",
        help="Dialogue voices: character_id:voice_id comma-separated (e.g. hero:nova,villain:onyx). Scenes with scene_type dialogue + character_id use these.",
    )
    parser.add_argument("--out-dir", default=None, help="Output directory for MP3s (default: scripts/out_tts)")
    parser.add_argument("--play", action="store_true", help="After generating, play all scenes in order (afplay or ffplay)")
    parser.add_argument("--play-only", action="store_true", help="Play existing scene_*.mp3 in out-dir; no TTS generation")
    args = parser.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "scripts" / "out_tts"

    if args.play_only:
        if not out_dir.is_dir():
            print(f"Directory not found: {out_dir}")
            print("Generate first: python3 scripts/test_story_tts.py")
            sys.exit(1)
        print(f"Playing story from {out_dir}...")
        play_story(out_dir)
        return

    scenes_path = Path(args.scenes_json)
    if not scenes_path.is_file():
        print(f"Scenes file not found: {scenes_path}")
        print("Run: python3 scripts/test_story_generation.py \"Your topic\"")
        sys.exit(1)

    import json
    with open(scenes_path) as f:
        scenes = json.load(f)
    if not isinstance(scenes, list) or not scenes:
        print("Scenes JSON must be a non-empty array of objects with 'text'.")
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    narrator_voice = (args.voice or "alloy").strip()
    character_voices = {}
    for part in (args.character_voices or "").strip().split(","):
        part = part.strip()
        if ":" in part:
            k, v = part.split(":", 1)
            if k.strip() and v.strip():
                character_voices[k.strip()] = v.strip()
    voice_language = {
        "narratorVoiceId": narrator_voice,
        "characterVoices": character_voices,
    } if character_voices else {"narratorVoiceId": narrator_voice}

    print(f"TTS for {len(scenes)} scenes → {out_dir}")
    print(f"  Narrator: {narrator_voice}")
    if character_voices:
        print(f"  Characters: {character_voices}")
    print()

    for i, scene in enumerate(scenes):
        text = (scene.get("text") or "").strip()
        if not text:
            continue
        num = i + 1
        voice_id = _voice_id_for_scene(voice_language, scene, narrator_voice)
        scene_type = (scene.get("scene_type") or "narration").lower()
        emotion_tag = (scene.get("emotion") or "").strip() if scene_type == "dialogue" else None
        out_path = out_dir / f"scene_{num:02d}.mp3"
        voice_label = voice_id if voice_id != narrator_voice else "narrator"
        print(f"  Scene {num} [{voice_label}]: {text[:50]}...")
        try:
            audio = synthesize(text, voice_id=voice_id, emotion_tag=emotion_tag or None)
            out_path.write_bytes(audio)
            print(f"    → {out_path}")
        except Exception as e:
            print(f"    ERROR: {e}")
            sys.exit(1)

    print()
    if args.play:
        print("Playing story in order...")
        play_story(out_dir)
    else:
        print("Done. Play with: open scripts/out_tts/scene_01.mp3 (or ffplay / your player)")
        print("  Or run with --play to listen in order: python3 scripts/test_story_tts.py --play")
        print("  Or play existing files only: python3 scripts/test_story_tts.py --play-only")


if __name__ == "__main__":
    main()
