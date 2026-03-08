"""
Unit tests for cost-effective TTS/voice: voice selection and ElevenLabs model choice.

No API calls, no DB.

Run as script (no pytest, from project root):  cd /path/to/BE-auto-viral && python3 tests/test_media_voice_and_tts.py
Or with pytest:  pytest tests/test_media_voice_and_tts.py -v
Use the same Python environment as the app (venv with boto3 etc.) so imports succeed.

What to test manually / in integration:
- TTS cache hit: run generate_media for an episode, then run again with the same
  script text and voice; second run should reuse cached audio (no new ElevenLabs call).
- TTS cache miss: new text or different voice should call TTS and then set cache.
- Emotion tag: scene with scene_type=dialogue and emotion set should pass emotion_tag
  into synthesize and use eleven_v3 for short lines (check logs or mock).
- End-to-end: one narrator (ELEVENLABS_VOICE_ID), 1–2 characterVoices, mix of
  narration and dialogue scenes; verify correct voice per scene and cache reuse.
"""

import os
import sys

if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, root)
    os.chdir(root)

from types import SimpleNamespace

from app.services.tts_service import get_elevenlabs_model_id_for_request
from app.workers.tasks.media import _voice_id_for_scene, _voice_id_from_series


# ---------------------------------------------------------------------------
# _voice_id_from_series
# ---------------------------------------------------------------------------


def test_voice_id_from_series_none_or_empty_returns_alloy():
    assert _voice_id_from_series(None) == "alloy"
    assert _voice_id_from_series({}) == "alloy"


def test_voice_id_from_series_female_warm_returns_nova():
    assert _voice_id_from_series({"gender": "female", "style": "warm"}) == "nova"


def test_voice_id_from_series_female_no_warm_returns_shimmer():
    assert _voice_id_from_series({"gender": "female"}) == "shimmer"
    assert _voice_id_from_series({"gender": "female", "style": "friendly"}) == "shimmer"


def test_voice_id_from_series_male_deep_returns_onyx():
    assert _voice_id_from_series({"gender": "male", "style": "deep"}) == "onyx"


def test_voice_id_from_series_male_no_deep_returns_echo():
    assert _voice_id_from_series({"gender": "male"}) == "echo"


def test_voice_id_from_series_neutral_returns_alloy():
    assert _voice_id_from_series({"gender": "neutral"}) == "alloy"


# ---------------------------------------------------------------------------
# _voice_id_for_scene
# ---------------------------------------------------------------------------


def test_voice_id_for_scene_no_voice_language_uses_series_style():
    assert _voice_id_for_scene(None, {}, "default-el-id") == "alloy"
    assert _voice_id_for_scene({}, {"text": "Hi"}, "") == "alloy"


def test_voice_id_for_scene_narrator_voice_id_used_for_narration():
    vl = {"narratorVoiceId": "narrator-el-id", "characterVoices": {"hero": "hero-el-id"}}
    scene = {"scene_type": "narration", "text": "Once upon a time."}
    assert _voice_id_for_scene(vl, scene, "env-default") == "narrator-el-id"


def test_voice_id_for_scene_default_elevenlabs_when_no_narrator_id():
    vl = {"characterVoices": {"hero": "hero-el-id"}}
    scene = {"scene_type": "narration"}
    assert _voice_id_for_scene(vl, scene, "env-default-id") == "env-default-id"


def test_voice_id_for_scene_dialogue_character_uses_character_voice():
    vl = {
        "narratorVoiceId": "narrator-el-id",
        "characterVoices": {"hero": "hero-el-id", "villain": "villain-el-id"},
    }
    scene = {"scene_type": "dialogue", "character_id": "hero", "text": "I will save the day."}
    assert _voice_id_for_scene(vl, scene, "env-default") == "hero-el-id"
    scene2 = {"scene_type": "dialogue", "character_id": "villain", "text": "Never."}
    assert _voice_id_for_scene(vl, scene2, "env-default") == "villain-el-id"


def test_voice_id_for_scene_dialogue_unknown_character_falls_back_to_narrator():
    vl = {"narratorVoiceId": "narrator-el-id", "characterVoices": {"hero": "hero-el-id"}}
    scene = {"scene_type": "dialogue", "character_id": "other", "text": "Hi."}
    assert _voice_id_for_scene(vl, scene, "env-default") == "narrator-el-id"


def test_voice_id_for_scene_dialogue_empty_character_voices_uses_narrator():
    vl = {"narratorVoiceId": "narrator-el-id", "characterVoices": {}}
    scene = {"scene_type": "dialogue", "character_id": "hero"}
    assert _voice_id_for_scene(vl, scene, "env-default") == "narrator-el-id"


def test_voice_id_for_scene_character_id_case_insensitive_lookup():
    vl = {"characterVoices": {"Hero": "hero-el-id"}}
    scene = {"scene_type": "dialogue", "character_id": "hero"}
    assert _voice_id_for_scene(vl, scene, "") == "hero-el-id"


# ---------------------------------------------------------------------------
# get_elevenlabs_model_id_for_request (cost-effective: v3 vs turbo)
# ---------------------------------------------------------------------------


def _settings(model_id: str = ""):
    return SimpleNamespace(elevenlabs_model_id=model_id)


def test_elevenlabs_model_short_emotional_uses_v3():
    s = _settings("eleven_turbo_v2_5")
    assert get_elevenlabs_model_id_for_request("Hi.", "whispers", s) == "eleven_v3"
    assert get_elevenlabs_model_id_for_request("x" * 500, "sad", s) == "eleven_v3"


def test_elevenlabs_model_long_text_uses_configured():
    s = _settings("eleven_turbo_v2_5")
    assert get_elevenlabs_model_id_for_request("x" * 501, "whispers", s) == "eleven_turbo_v2_5"
    assert get_elevenlabs_model_id_for_request("Long narration " * 100, None, s) == "eleven_turbo_v2_5"


def test_elevenlabs_model_no_emotion_uses_configured():
    s = _settings("eleven_multilingual_v2")
    assert get_elevenlabs_model_id_for_request("Short line.", None, s) == "eleven_multilingual_v2"
    assert get_elevenlabs_model_id_for_request("Short.", "", s) == "eleven_multilingual_v2"


def test_elevenlabs_model_empty_config_defaults_to_multilingual_v2():
    s = _settings("")
    assert get_elevenlabs_model_id_for_request("Long text.", None, s) == "eleven_multilingual_v2"


# ---------------------------------------------------------------------------
# TTS cache: hash consistency (no DB)
# ---------------------------------------------------------------------------
# get_cached_tts_asset_id / set_cached_tts_asset_id require a real DB session
# and assets; test those in integration tests or manually. Here we only
# verify the cache key is deterministic by testing that the same (text, voice_id)
# would be looked up with the same hash. We do that by importing the private
# _text_hash and testing it (or skip and document below).


def test_tts_cache_hash_deterministic():
    from app.services.cache.tts_cache import _text_hash
    h1 = _text_hash("Hello world", "voice-1")
    h2 = _text_hash("Hello world", "voice-1")
    assert h1 == h2
    assert _text_hash("Hello world", "voice-2") != h1
    assert _text_hash("Hello world ", "voice-1") == h1  # strip


if __name__ == "__main__":
    tests = [
        test_voice_id_from_series_none_or_empty_returns_alloy,
        test_voice_id_from_series_female_warm_returns_nova,
        test_voice_id_from_series_female_no_warm_returns_shimmer,
        test_voice_id_from_series_male_deep_returns_onyx,
        test_voice_id_from_series_male_no_deep_returns_echo,
        test_voice_id_from_series_neutral_returns_alloy,
        test_voice_id_for_scene_no_voice_language_uses_series_style,
        test_voice_id_for_scene_narrator_voice_id_used_for_narration,
        test_voice_id_for_scene_default_elevenlabs_when_no_narrator_id,
        test_voice_id_for_scene_dialogue_character_uses_character_voice,
        test_voice_id_for_scene_dialogue_unknown_character_falls_back_to_narrator,
        test_voice_id_for_scene_dialogue_empty_character_voices_uses_narrator,
        test_voice_id_for_scene_character_id_case_insensitive_lookup,
        test_elevenlabs_model_short_emotional_uses_v3,
        test_elevenlabs_model_long_text_uses_configured,
        test_elevenlabs_model_no_emotion_uses_configured,
        test_elevenlabs_model_empty_config_defaults_to_multilingual_v2,
        test_tts_cache_hash_deterministic,
    ]
    for t in tests:
        t()
        print(f"  ok {t.__name__}")
    print("All tests passed.")
