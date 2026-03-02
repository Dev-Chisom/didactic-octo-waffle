from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Pricing:
    # This is intentionally a rough default. You can override via CLI flags.
    #
    # Example ballpark for SDXL via a hosted inference API:
    # - $0.01–$0.03 per image depending on provider, size, steps.
    sdxl_cost_per_image_usd: float = 0.015
    # OpenAI narration LLM (gpt-4o-mini): ~$0.001 per call (one call per part).
    narration_llm_cost_per_call_usd: float = 0.001
    # OpenAI TTS (tts-1): $15 per 1M characters.
    openai_tts_cost_per_1m_chars_usd: float = 15.0


@dataclass(frozen=True)
class Paths:
    repo_root: Path
    assets_dir: Path
    runs_dir: Path
    image_cache_dir: Path
    music_dir: Path
    fonts_dir: Path


@dataclass(frozen=True)
class AppConfig:
    paths: Paths
    pricing: Pricing
    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"


def default_config(repo_root: Path) -> AppConfig:
    assets_dir = repo_root / "assets"
    return AppConfig(
        paths=Paths(
            repo_root=repo_root,
            assets_dir=assets_dir,
            runs_dir=repo_root / "runs",
            image_cache_dir=assets_dir / "images",
            music_dir=assets_dir / "music",
            fonts_dir=assets_dir / "fonts",
        ),
        pricing=Pricing(),
    )

