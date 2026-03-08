#!/usr/bin/env python3
"""
Run cheap pipeline tests without pytest. No API, no DB.

Usage (from project root): python3 tests/run_cheap_tests.py
Or:    cd /path/to/BE-auto-viral && PYTHONPATH=. python3 tests/run_cheap_tests.py
"""

from __future__ import annotations

import sys

# Ensure app is on path when run as script (from project root or from tests/)
if __name__ == "__main__":
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, root)
    os.chdir(root)

from app.schemas.script_scenes import (
    DEFAULT_ANIMATION,
    dialogue_expansion_to_scenes,
    normalize_animation,
    validate_scenes,
)
from app.utils.ffmpeg_filters import zoompan_vf as _zoompan_vf


def test_normalize_animation():
    assert normalize_animation(None) == DEFAULT_ANIMATION
    assert normalize_animation({}) == DEFAULT_ANIMATION
    out = normalize_animation({"motion": "zoom_in", "zoom_start": 1.0, "zoom_end": 1.3})
    assert out["motion"] == "zoom_in"
    assert out["zoom_start"] == 1.0
    assert out["zoom_end"] == 1.3
    out = normalize_animation({"motion": "invalid_motion"})
    assert out["motion"] == "ken_burns_zoom"
    out = normalize_animation({"motion": "static"})
    assert out["motion"] == "static"
    print("  ok normalize_animation")


def test_validate_scenes():
    out = validate_scenes([{"text": "Hello world", "visual_description": "a beach"}])
    assert len(out) == 1
    assert out[0]["text"] == "Hello world"
    assert out[0]["visual_description"] == "a beach"
    assert out[0]["scene_type"] == "narration"
    assert out[0]["scene"] == 1

    out = validate_scenes([{"text": "Hi", "image_prompt": "sunset over mountains"}])
    assert out[0]["visual_description"] == "sunset over mountains"

    try:
        validate_scenes([{"text": "I said it.", "scene_type": "dialogue"}])
        assert False, "expected ValueError"
    except ValueError as e:
        assert "character_id" in str(e)

    out = validate_scenes([{"text": "We must go.", "scene_type": "dialogue", "character_id": "hero"}])
    assert len(out) == 1
    assert out[0]["scene_type"] == "dialogue"
    assert out[0]["character_id"] == "hero"

    out = validate_scenes([
        {"text": "Scene one", "visual_description": "forest", "animation": {"motion": "zoom_out", "zoom_end": 1.0}}
    ])
    assert out[0]["animation"]["motion"] == "zoom_out"
    assert out[0]["animation"]["zoom_end"] == 1.0

    for bad in ([], [{"visual_description": "only"}]):
        try:
            validate_scenes(bad if isinstance(bad, list) else [bad])
            assert False, f"expected ValueError for {bad}"
        except ValueError:
            pass
    print("  ok validate_scenes")


def test_dialogue_expansion_to_scenes():
    expanded = [{"scene_number": 1, "narration": "The jungle was silent.", "dialogue": [], "image_prompt": "dark jungle"}]
    out = dialogue_expansion_to_scenes(expanded, use_dialogue_scenes=True)
    assert len(out) == 1
    assert out[0]["text"] == "The jungle was silent."
    assert out[0]["scene_type"] == "narration"
    assert out[0]["visual_description"] == "dark jungle"

    expanded = [{
        "scene_number": 1,
        "narration": "Kairo stood at the temple.",
        "dialogue": [
            {"character": "Tala", "character_id": "tala", "emotion": "angry", "line": "Let me through."},
            {"character": "Kairo", "character_id": "kairo", "emotion": "calm", "line": "No."},
        ],
        "image_prompt": "temple entrance",
    }]
    out = dialogue_expansion_to_scenes(expanded, use_dialogue_scenes=True)
    assert len(out) == 3
    assert out[0]["text"] == "Kairo stood at the temple."
    assert out[0]["scene_type"] == "narration"
    assert out[1]["text"] == "Let me through."
    assert out[1]["scene_type"] == "dialogue"
    assert out[1]["character_id"] == "tala"
    assert out[2]["text"] == "No."
    assert out[2]["character_id"] == "kairo"

    expanded = [{"scene_number": 2, "narration": "", "dialogue": [{"character_id": "kairo", "line": "Go."}], "visual_prompt": "cave"}]
    out = dialogue_expansion_to_scenes(expanded, image_prompt_key="visual_prompt", use_dialogue_scenes=True)
    assert len(out) == 1
    assert out[0]["text"] == "Go."
    assert out[0]["character_id"] == "kairo"
    assert out[0]["visual_description"] == "cave"

    expanded = [{
        "scene_number": 1,
        "narration": "They faced each other.",
        "dialogue": [{"character_id": "a", "line": "Hi."}, {"character_id": "b", "line": "Bye."}],
        "image_prompt": "room",
    }]
    out = dialogue_expansion_to_scenes(expanded, use_dialogue_scenes=False)
    assert len(out) == 1
    assert "They faced each other." in out[0]["text"]
    assert "Hi." in out[0]["text"]
    assert "Bye." in out[0]["text"]
    assert out[0]["scene_type"] == "narration"
    print("  ok dialogue_expansion_to_scenes")


def test_zoompan_vf():
    vf = _zoompan_vf(5.0, None)
    assert "scale=1080:1920" in vf
    assert "pad=1080:1920" in vf
    assert "zoompan" in vf
    assert "fps=30" in vf
    assert "1.2" in vf

    vf = _zoompan_vf(10.0, {"zoom_start": 1.0, "zoom_end": 1.5})
    assert "1.5" in vf

    vf = _zoompan_vf(5.0, {"motion": "static", "zoom_start": 1.1})
    assert "1.1" in vf

    vf = _zoompan_vf(0.5, None)
    assert "zoompan" in vf and "1080x1920" in vf
    print("  ok _zoompan_vf")


def main():
    print("Running cheap pipeline tests (no API, no DB)...")
    test_normalize_animation()
    test_validate_scenes()
    test_dialogue_expansion_to_scenes()
    test_zoompan_vf()
    print("All cheap tests passed.")


if __name__ == "__main__":
    main()
