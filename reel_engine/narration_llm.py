from __future__ import annotations

"""
reel_engine/narration_llm.py

Generates per-shot narration lines via an LLM API call (OpenAI).
- Single call per plan (all shots at once) — keeps latency and cost low.
- Disk-caches results keyed on style + topic + shot specs so repeat
  requests never hit the API twice.
- Returns None on any failure so the caller can fall back gracefully.
"""

import json
import logging
import os
from hashlib import sha1
from pathlib import Path
from typing import Optional

from openai import OpenAI

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_narration_lines(
    *,
    style_key: str,
    topic: str,
    shot_specs: list[dict],
    part_index: int,
    parts_total: int,
    part_label: str,
    cache_dir: Optional[Path] = None,
    previous_part_summary: Optional[str] = None,
) -> Optional[list[str]]:
    """
    Returns a list of narration strings, one per shot, or None on failure.

    shot_specs is a list of dicts with keys:
        shot_id, visual_beat, emotion, arc_position
    """
    num_shots = len(shot_specs)
    if num_shots == 0:
        return None

    cache_key = _build_cache_key(
        style_key=style_key,
        topic=topic,
        shot_specs=shot_specs,
        part_index=part_index,
        parts_total=parts_total,
        previous_part_summary=previous_part_summary,
    )

    # Cache read
    if cache_dir:
        cached = _read_cache(cache_dir, cache_key)
        if cached is not None:
            if len(cached) == num_shots:
                log.debug("narration cache hit: %s", cache_key[:12])
                return cached
            log.warning("cached narration length mismatch — regenerating")

    lines = _call_api(
        style_key=style_key,
        topic=topic,
        shot_specs=shot_specs,
        part_index=part_index,
        parts_total=parts_total,
        part_label=part_label,
        num_shots=num_shots,
        previous_part_summary=previous_part_summary,
    )

    if lines is None:
        return None

    # Cache write
    if cache_dir:
        _write_cache(cache_dir, cache_key, lines)

    return lines


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a professional short-form video scriptwriter specialising in \
high-retention content for social media reels and YouTube Shorts. \
You write narration lines that stop the scroll.

Rules:
- One line per shot. Maximum 12 words. No exceptions.
- Every line must reference the topic directly or obliquely — never generic filler.
- The line must feel connected to what is visible on screen (the visual beat).
- Match emotional tone to arc position:
    hook      → create dread / curiosity / urgency in the first second
    setup     → ground the viewer in the specific world of this topic
    build     → raise a question or introduce a complication
    escalate  → raise the stakes; something shifts
    twist     → reframe what the viewer thought they knew
    resolve   → pay off the promise; leave them satisfied or wanting more
- Never use: "this changed everything", "you won't believe", "let's dive in", \
or any phrase that sounds like a generic YouTube tutorial.
- Write as if you are the viewer's most interesting friend, not a content creator.
- Tone per style:
    horror   → dread and unease, understated
    crime    → cold, investigative, precise
    anime    → high-stakes, personal, emotionally charged
    cartoon  → wonder and playful stakes, light energy
    faceless → direct and motivational, never cringe
- Output ONLY a JSON array of strings, one per shot, in order.
  No explanation, no markdown fences, no extra keys. Raw JSON only.
"""


def _call_api(
    *,
    style_key: str,
    topic: str,
    shot_specs: list[dict],
    part_index: int,
    parts_total: int,
    part_label: str,
    num_shots: int,
    previous_part_summary: Optional[str] = None,
) -> Optional[list[str]]:
    api_key = _get_api_key()
    if not api_key:
        log.warning("OPENAI_API_KEY not set — narration will fall back to templates")
        return None

    part_note = (
        f"This is part {part_index} of {parts_total}. Part label: \"{part_label}\"."
        if parts_total > 1
        else "Single-part video."
    )
    continuation_note = ""
    if parts_total > 1 and part_index > 1 and (previous_part_summary or "").strip():
        continuation_note = (
            f"\n\nCONTINUATION: This part must continue the same story. "
            "Do NOT repeat the setup or introduce the same characters again. "
            "Pick up from where the previous part left off.\n\n"
            f"What happened in the previous part (end of script):\n\"\"\"\n{previous_part_summary.strip()}\n\"\"\"\n\n"
        )

    user_prompt = (
        f"Generate narration lines for a **{style_key}** style video about: \"{topic}\".\n\n"
        f"{part_note}{continuation_note}\n"
        f"Shots: {num_shots}\n\n"
        "Shot details (in order):\n"
        + json.dumps(shot_specs, indent=2)
        + f"\n\nReturn a JSON array of exactly {num_shots} strings."
    )

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=_get_model(),
            max_tokens=512,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = (response.choices[0].message.content or "").strip()
        return _parse_response(raw, num_shots)

    except Exception as exc:  # noqa: BLE001
        log.warning("narration LLM: %s — %s", type(exc).__name__, exc)

    return None


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _parse_response(raw: str, expected: int) -> Optional[list[str]]:
    """
    Strip markdown fences if present, parse JSON array, validate length.
    Returns None rather than raising so the caller falls back cleanly.
    """
    # Strip ```json ... ``` or ``` ... ``` wrappers
    text = raw
    if text.startswith("```"):
        text = text.split("```", 2)[-1] if text.count("```") >= 2 else text
        text = text.lstrip("json").strip().rstrip("`").strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        log.warning("narration LLM: JSON parse failed — %s | raw: %.120s", exc, raw)
        return None

    if not isinstance(data, list):
        log.warning("narration LLM: expected list, got %s", type(data).__name__)
        return None

    lines = [str(item).strip() for item in data]

    if len(lines) != expected:
        log.warning(
            "narration LLM: expected %d lines, got %d", expected, len(lines)
        )
        # Tolerate off-by-one: trim or pad with empty strings and let
        # the caller's length check decide whether to fall back.
        if abs(len(lines) - expected) <= 2:
            while len(lines) < expected:
                lines.append("")
            lines = lines[:expected]
        else:
            return None

    return lines


# ---------------------------------------------------------------------------
# Disk cache helpers
# ---------------------------------------------------------------------------


def _build_cache_key(
    *,
    style_key: str,
    topic: str,
    shot_specs: list[dict],
    part_index: int,
    parts_total: int,
    previous_part_summary: Optional[str] = None,
) -> str:
    payload = json.dumps(
        {
            "style": style_key,
            "topic": topic,
            "part": f"{part_index}/{parts_total}",
            "shots": shot_specs,
            "prev_summary": (previous_part_summary or "")[:500],
        },
        sort_keys=True,
    )
    return sha1(payload.encode()).hexdigest()


def _read_cache(cache_dir: Path, key: str) -> Optional[list[str]]:
    path = cache_dir / f"narration_{key}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("narration cache read error: %s", exc)
        return None


def _write_cache(cache_dir: Path, key: str, lines: list[str]) -> None:
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / f"narration_{key}.json"
        path.write_text(json.dumps(lines, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("narration cache write error: %s", exc)


# ---------------------------------------------------------------------------
# Config helpers — read from env so nothing is hardcoded
# ---------------------------------------------------------------------------


def _get_api_key() -> Optional[str]:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    return key or None


def _get_model() -> str:
    return os.environ.get("NARRATION_LLM_MODEL", "gpt-4o-mini")
