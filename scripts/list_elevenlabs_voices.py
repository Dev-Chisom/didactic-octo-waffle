#!/usr/bin/env python3
"""
List your ElevenLabs voices (voice_id + name) so you can pick IDs for narrator/characters.

Usage (from project root): python3 scripts/list_elevenlabs_voices.py

Requires: ELEVENLABS_API_KEY in .env
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings
import httpx


def main() -> None:
    settings = get_settings()
    api_key = (settings.elevenlabs_api_key or "").strip()
    if not api_key:
        print("ELEVENLABS_API_KEY not set in .env")
        sys.exit(1)

    base = (settings.elevenlabs_base_url or "https://api.elevenlabs.io/v1").rstrip("/")
    url = f"{base}/voices"
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        print(f"API error: {e.response.status_code} {e.response.text[:200]}")
        sys.exit(1)
    except Exception as e:
        print(f"Request failed: {e}")
        sys.exit(1)

    voices = data.get("voices") if isinstance(data, dict) else data
    if not isinstance(voices, list):
        print("Unexpected response format")
        sys.exit(1)

    print(f"Found {len(voices)} voices. Use voice_id for ELEVENLABS_VOICE_ID or character maps.\n")
    print(f"{'voice_id':<36}  name")
    print("-" * 60)
    for v in voices:
        if not isinstance(v, dict):
            continue
        vid = v.get("voice_id") or v.get("id") or ""
        name = v.get("name") or ""
        labels = v.get("labels") or {}
        extra = ""
        if isinstance(labels, dict):
            gender = labels.get("gender", "")
            if gender:
                extra = f"  ({gender})"
        print(f"{vid:<36}  {name}{extra}")
    print("\nCopy a voice_id into .env as ELEVENLABS_VOICE_ID or into series.voice_language.characterVoices.")


if __name__ == "__main__":
    main()
