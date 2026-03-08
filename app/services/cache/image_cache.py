"""
Scene image cache: reuse generated images by prompt + style to reduce Replicate cost.

Cache key: hash(visual_description + style_seed + optional series_style).
Lookup by workspace_id + metadata.prompt_hash (and optionally style) in Asset table,
or use Redis for faster lookup: key "img:{workspace_id}:{prompt_hash}" -> asset_id.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models.asset import Asset


def _prompt_hash(prompt: str, style_seed: str = "") -> str:
    raw = f"{prompt.strip()}|{style_seed}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def get_cached_image_asset_id(
    db: Session,
    workspace_id: uuid.UUID,
    visual_description: str,
    style_seed: str = "",
    metadata_key: str = "prompt_hash",
) -> Optional[uuid.UUID]:
    """
    Return existing image asset_id if we have one for this prompt+style; else None.
    Assets must be stored with metadata_["prompt_hash"] = _prompt_hash(visual_description, style_seed).
    """
    prompt_hash = _prompt_hash(visual_description, style_seed)
    row = (
        db.query(Asset.id)
        .filter(
            Asset.workspace_id == workspace_id,
            Asset.type == "image",
            Asset.source == "generated",
            Asset.metadata_.isnot(None),
        )
        .filter(Asset.metadata_["prompt_hash"].astext == prompt_hash)
        .order_by(Asset.created_at.desc())
        .first()
    )
    return row[0] if row else None


def set_cached_image_asset_id(
    db: Session,
    workspace_id: uuid.UUID,
    asset_id: uuid.UUID,
    visual_description: str,
    style_seed: str = "",
) -> None:
    """
    Mark an asset as cacheable by updating its metadata with prompt_hash.
    Call after uploading a new generated image so future lookups can reuse it.
    """
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.workspace_id == workspace_id).first()
    if not asset or asset.type != "image":
        return
    meta = dict(asset.metadata_ or {})
    meta["prompt_hash"] = _prompt_hash(visual_description, style_seed)
    asset.metadata_ = meta
    db.flush()
