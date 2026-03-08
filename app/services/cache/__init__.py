"""
Asset cache for long-form video cost optimization.

- image_cache: lookup by (prompt_hash, style) to reuse scene images.
- tts_cache: lookup by (text_hash, voice_id) to reuse narration/dialogue audio.
- character_cache: lookup by (series_id, character_id) to reuse character face image.

Use get_* before calling Replicate/ElevenLabs; call set_* (or store asset with
metadata) after generating so future episodes can reuse.
"""

from app.services.cache.character_cache import get_character_asset_id, set_character_asset_id
from app.services.cache.image_cache import get_cached_image_asset_id, set_cached_image_asset_id
from app.services.cache.tts_cache import get_cached_tts_asset_id, set_cached_tts_asset_id

__all__ = [
    "get_cached_image_asset_id",
    "set_cached_image_asset_id",
    "get_cached_tts_asset_id",
    "set_cached_tts_asset_id",
    "get_character_asset_id",
    "set_character_asset_id",
]
