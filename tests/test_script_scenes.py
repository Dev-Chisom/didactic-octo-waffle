"""
Tests for cheap pipeline pieces: scene validation, animation, dialogue→scenes mapping.
No API calls, no DB required.
"""

import pytest

from app.schemas.script_scenes import (
    DEFAULT_ANIMATION,
    dialogue_expansion_to_scenes,
    normalize_animation,
    validate_scenes,
)


# ---------------------------------------------------------------------------
# normalize_animation
# ---------------------------------------------------------------------------


def test_normalize_animation_empty_returns_defaults():
    assert normalize_animation(None) == DEFAULT_ANIMATION
    assert normalize_animation({}) == DEFAULT_ANIMATION


def test_normalize_animation_valid_motion():
    out = normalize_animation({"motion": "zoom_in", "zoom_start": 1.0, "zoom_end": 1.3})
    assert out["motion"] == "zoom_in"
    assert out["zoom_start"] == 1.0
    assert out["zoom_end"] == 1.3


def test_normalize_animation_invalid_motion_falls_back_to_ken_burns():
    out = normalize_animation({"motion": "invalid_motion"})
    assert out["motion"] == "ken_burns_zoom"


def test_normalize_animation_static():
    out = normalize_animation({"motion": "static"})
    assert out["motion"] == "static"


# ---------------------------------------------------------------------------
# validate_scenes
# ---------------------------------------------------------------------------


def test_validate_scenes_minimal():
    raw = [{"text": "Hello world", "visual_description": "a beach"}]
    out = validate_scenes(raw)
    assert len(out) == 1
    assert out[0]["text"] == "Hello world"
    assert out[0]["visual_description"] == "a beach"
    assert out[0]["scene_type"] == "narration"
    assert out[0]["scene"] == 1


def test_validate_scenes_uses_image_prompt_if_no_visual_description():
    raw = [{"text": "Hi", "image_prompt": "sunset over mountains"}]
    out = validate_scenes(raw)
    assert out[0]["visual_description"] == "sunset over mountains"


def test_validate_scenes_dialogue_requires_character_id():
    raw = [{"text": "I said it.", "scene_type": "dialogue"}]
    with pytest.raises(ValueError, match="character_id"):
        validate_scenes(raw)


def test_validate_scenes_dialogue_with_character_id():
    raw = [{"text": "We must go.", "scene_type": "dialogue", "character_id": "hero"}]
    out = validate_scenes(raw)
    assert len(out) == 1
    assert out[0]["scene_type"] == "dialogue"
    assert out[0]["character_id"] == "hero"


def test_validate_scenes_animation_normalized():
    raw = [
        {
            "text": "Scene one",
            "visual_description": "forest",
            "animation": {"motion": "zoom_out", "zoom_end": 1.0},
        }
    ]
    out = validate_scenes(raw)
    assert out[0]["animation"]["motion"] == "zoom_out"
    assert out[0]["animation"]["zoom_end"] == 1.0


def test_validate_scenes_empty_list_raises():
    with pytest.raises(ValueError, match="non-empty list"):
        validate_scenes([])


def test_validate_scenes_missing_text_raises():
    with pytest.raises(ValueError, match="missing 'text'"):
        validate_scenes([{"visual_description": "only visual"}])


# ---------------------------------------------------------------------------
# dialogue_expansion_to_scenes
# ---------------------------------------------------------------------------


def test_dialogue_expansion_narration_only():
    expanded = [
        {
            "scene_number": 1,
            "narration": "The jungle was silent.",
            "dialogue": [],
            "image_prompt": "dark jungle at night",
        }
    ]
    out = dialogue_expansion_to_scenes(expanded, use_dialogue_scenes=True)
    assert len(out) == 1
    assert out[0]["text"] == "The jungle was silent."
    assert out[0]["scene_type"] == "narration"
    assert out[0]["visual_description"] == "dark jungle at night"


def test_dialogue_expansion_narration_plus_dialogue_use_dialogue_scenes():
    expanded = [
        {
            "scene_number": 1,
            "narration": "Kairo stood at the temple entrance.",
            "dialogue": [
                {"character": "Tala", "character_id": "tala", "emotion": "angry", "line": "Let me through."},
                {"character": "Kairo", "character_id": "kairo", "emotion": "calm", "line": "No."},
            ],
            "image_prompt": "temple entrance",
        }
    ]
    out = dialogue_expansion_to_scenes(expanded, use_dialogue_scenes=True)
    assert len(out) == 3
    assert out[0]["text"] == "Kairo stood at the temple entrance."
    assert out[0]["scene_type"] == "narration"
    assert out[1]["text"] == "Let me through."
    assert out[1]["scene_type"] == "dialogue"
    assert out[1]["character_id"] == "tala"
    assert out[2]["text"] == "No."
    assert out[2]["character_id"] == "kairo"


def test_dialogue_expansion_no_narration_only_dialogue():
    expanded = [
        {
            "scene_number": 2,
            "narration": "",
            "dialogue": [{"character_id": "kairo", "line": "Go."}],
            "visual_prompt": "cave",
        }
    ]
    out = dialogue_expansion_to_scenes(
        expanded, image_prompt_key="visual_prompt", use_dialogue_scenes=True
    )
    assert len(out) == 1
    assert out[0]["text"] == "Go."
    assert out[0]["scene_type"] == "dialogue"
    assert out[0]["character_id"] == "kairo"
    assert out[0]["visual_description"] == "cave"


def test_dialogue_expansion_use_dialogue_scenes_false_combines_text():
    expanded = [
        {
            "scene_number": 1,
            "narration": "They faced each other.",
            "dialogue": [
                {"character_id": "a", "line": "Hi."},
                {"character_id": "b", "line": "Bye."},
            ],
            "image_prompt": "room",
        }
    ]
    out = dialogue_expansion_to_scenes(expanded, use_dialogue_scenes=False)
    assert len(out) == 1
    assert "They faced each other." in out[0]["text"]
    assert "Hi." in out[0]["text"]
    assert "Bye." in out[0]["text"]
    assert out[0]["scene_type"] == "narration"


def test_dialogue_expansion_skips_empty_lines():
    expanded = [
        {
            "scene_number": 1,
            "narration": "Okay.",
            "dialogue": [{"character_id": "x", "line": ""}, {"character_id": "x", "line": "Real line."}],
            "image_prompt": "street",
        }
    ]
    out = dialogue_expansion_to_scenes(expanded, use_dialogue_scenes=True)
    assert len(out) == 2  # narration + one dialogue
    assert out[1]["text"] == "Real line."


def test_dialogue_expansion_character_id_from_character_name():
    expanded = [
        {
            "scene_number": 1,
            "narration": "",
            "dialogue": [{"character": "Kairo", "line": "I am here."}],  # no character_id
            "image_prompt": "jungle",
        }
    ]
    out = dialogue_expansion_to_scenes(expanded, use_dialogue_scenes=True)
    assert out[0]["character_id"] == "kairo"  # slug from name
