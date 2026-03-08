"""
Character image cache: one face image per character per series for lip-sync consistency.

Cache key: (series_id, character_id).
Lookup by Asset with type=image, source=generated, metadata.character_id and metadata.series_id
(or workspace_id + character_id).
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models.asset import Asset


def get_character_asset_id(
    db: Session,
    workspace_id: uuid.UUID,
    series_id: uuid.UUID,
    character_id: str,
) -> Optional[uuid.UUID]:
    """
    Return existing image asset_id for this series+character; else None.
    Use for dialogue scenes to reuse the same face across scenes.
    """
    if not (character_id or "").strip():
        return None
    row = (
        db.query(Asset.id)
        .filter(
            Asset.workspace_id == workspace_id,
            Asset.type == "image",
            Asset.source == "generated",
            Asset.metadata_.isnot(None),
        )
        .filter(
            Asset.metadata_["character_id"].astext == character_id.strip(),
            Asset.metadata_["series_id"].astext == str(series_id),
        )
        .order_by(Asset.created_at.desc())
        .first()
    )
    return row[0] if row else None


def set_character_asset_id(
    db: Session,
    workspace_id: uuid.UUID,
    asset_id: uuid.UUID,
    series_id: uuid.UUID,
    character_id: str,
) -> None:
    """
    Mark an image asset as the canonical character image for this series+character.
    Call after generating the first character image so all dialogue scenes reuse it.
    """
    if not (character_id or "").strip():
        return
    asset = db.query(Asset).filter(Asset.id == asset_id, Asset.workspace_id == workspace_id).first()
    if not asset or asset.type != "image":
        return
    meta = dict(asset.metadata_ or {})
    meta["character_id"] = character_id.strip()
    meta["series_id"] = str(series_id)
    asset.metadata_ = meta
    db.flush()
