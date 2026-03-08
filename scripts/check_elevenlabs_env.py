#!/usr/bin/env python3
"""
Check that ElevenLabs env vars are loaded (no secrets printed).
Run (from project root): python3 scripts/check_elevenlabs_env.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings

def main():
    s = get_settings()
    key = (s.elevenlabs_api_key or "").strip()
    voice = (s.elevenlabs_voice_id or "").strip()
    model = (s.elevenlabs_model_id or "").strip()
    provider = getattr(s, "tts_provider", "openai")

    print("TTS_PROVIDER:", provider)
    print("ELEVENLABS_API_KEY: set=", bool(key), ", len=", len(key), "(expected ~52 for ElevenLabs)")
    print("ELEVENLABS_VOICE_ID: set=", bool(voice), ", value=", voice[:8] + "..." if len(voice) > 8 else voice)
    print("ELEVENLABS_MODEL_ID:", model or "(default)")

    if not key:
        print("\n→ ELEVENLABS_API_KEY is empty. Check .env: no spaces around =, key on one line.")
    elif len(key) < 40:
        print("\n→ Key looks short; copy the full key from ElevenLabs (Developers > API Keys).")
    if key and provider == "elevenlabs":
        print("\nIf you get 401 Unauthorized:")
        print("  • Get a fresh key: https://elevenlabs.io/app/settings/api-keys — Create/regenerate and paste the full key.")
        print("  • Old keys stop working after regeneration. No quotes in .env; key must be on a single line.")

if __name__ == "__main__":
    main()
