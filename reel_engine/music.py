from __future__ import annotations

from pathlib import Path
from typing import Optional

from reel_engine.utils import pick_random


def pick_music_track(*, music_root: Path, style: str, seed: int) -> Optional[Path]:
    """
    Pick a background music file from:
    - assets/music/{style}/
    - else assets/music/generic/

    Returns None if no music is available.
    """
    style_dir = (music_root / style).resolve()
    generic_dir = (music_root / "generic").resolve()

    candidates = _list_audio_files(style_dir)
    if not candidates:
        candidates = _list_audio_files(generic_dir)
    if not candidates:
        return None
    chosen = pick_random([str(p) for p in candidates], seed=seed)
    return Path(chosen)


def _list_audio_files(dir_path: Path) -> list[Path]:
    if not dir_path.exists() or not dir_path.is_dir():
        return []
    out: list[Path] = []
    for p in dir_path.iterdir():
        if p.is_file() and p.suffix.lower() in {".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg"}:
            out.append(p)
    return sorted(out)

