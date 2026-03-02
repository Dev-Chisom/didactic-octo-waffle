from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostReport:
    # Images (Replicate SDXL or other provider)
    images_new: int
    cost_per_image_usd: float
    images_cost_usd: float
    # Narration LLM (OpenAI, one call per part; cache hits reduce actual cost)
    narration_llm_calls: int
    narration_llm_cost_usd: float
    # OpenAI TTS (per character)
    tts_chars: int
    tts_cost_usd: float
    # Total
    total_cost_usd: float


def estimate_cost(
    *,
    images_new: int,
    cost_per_image_usd: float,
    narration_llm_calls: int = 0,
    cost_per_narration_call_usd: float = 0.001,
    tts_chars: int = 0,
    tts_cost_per_1m_chars_usd: float = 15.0,
) -> CostReport:
    """
    Build a cost report for Replicate (images) + narration LLM + OpenAI TTS.

    Pass narration_llm_calls=0 and tts_chars=0 when those features are not used.
    """
    images_cost = float(images_new) * float(cost_per_image_usd)
    narration_llm_cost = int(narration_llm_calls) * float(cost_per_narration_call_usd)
    tts_cost = (int(tts_chars) / 1_000_000.0) * float(tts_cost_per_1m_chars_usd)
    total = images_cost + narration_llm_cost + tts_cost

    return CostReport(
        images_new=int(images_new),
        cost_per_image_usd=float(cost_per_image_usd),
        images_cost_usd=round(images_cost, 4),
        narration_llm_calls=int(narration_llm_calls),
        narration_llm_cost_usd=round(narration_llm_cost, 4),
        tts_chars=int(tts_chars),
        tts_cost_usd=round(tts_cost, 4),
        total_cost_usd=round(total, 4),
    )
