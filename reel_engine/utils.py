from __future__ import annotations

import hashlib
import json
import os
import random
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Optional


def now_compact() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def stable_hash_int(text: str, *, bits: int = 31) -> int:
    # Deterministic across machines/runs (unlike Python's built-in hash()).
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], "big")
    return value & ((1 << bits) - 1)


def sha1_hex(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def pick_random(items: list[str], seed: int) -> str:
    if not items:
        raise ValueError("pick_random() received an empty list")
    rng = random.Random(seed)
    return rng.choice(items)


def write_json(path: Path, data: Any) -> None:
    def _default(o: Any) -> Any:
        if is_dataclass(o):
            return asdict(o)
        if isinstance(o, Path):
            return str(o)
        raise TypeError(f"Not JSON serializable: {type(o)}")

    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=_default) + "\n")


def read_env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))

