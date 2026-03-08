"""
TTS cache: reuse narration/dialogue audio by text + voice to reduce ElevenLabs/OpenAI cost.

Cache key: hash(text + voice_id).
Lookup by workspace_id + metadata.text_hash in Asset table,
or Redis: key "tts:{workspace_id}:{text_hash}:{voice_id}" -> asset_id.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models.asset import Asset


def _text_hash(text: str, voice_id: str) -> str:
    raw = f"{text.strip()}|{voice_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def get_cached_tts_asset_id(
    db: Session,
    workspace_id: uuid.UUID,
    text: str,
    voice_id: str,
) -> Optional[uuid.UUID]:
    """
    Return existing audio asset_id if we have one for this text+voice; else None.
    Assets must be stored with metadata_["text_hash"] and optionally ["voice_id"].
    """
    text_hash = _text_hash(text, voice_id)
    row = (
        db.query(Asset.id)
        .filter(
            Asset.workspace_id == workspace_id,
            Asset.type == "audio",
            Asset.source == "generated",
            Asset.metadata_.isnot(None),
        )
        .filter(Asset.metadata_["text_hash"].astext == text_hash)
        .order_by(Asset.created_at.desc())
        .first()
    )
    return row[0] if row else None


def set_cached_tts_asset_id(
    db: Session,
    workspace_id: uuid.UUID,
    asset_id: uuid.UUID,
    text: str,
    voice_id: str,
) -> None:
    """
    Mark an audio asset as cacheable by setting metadata text_hash (and voice_id).
    Call after uploading TTS so future episodes can reuse.
    """
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.workspace_id == workspace_id).first()
    if not asset or asset.type != "audio":
        return
    meta = dict(asset.metadata_ or {})
    meta["text_hash"] = _text_hash(text, voice_id)
    meta["voice_id"] = voice_id
    asset.metadata_ = meta
    db.flush()
