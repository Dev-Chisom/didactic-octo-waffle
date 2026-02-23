from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from openai import OpenAI

from app.config import get_settings
from app.schemas.script_scenes import SceneSpec, validate_scenes

logger = logging.getLogger(__name__)


def get_openai_client() -> OpenAI:
    settings = get_settings()
    client_kwargs = {
        "api_key": settings.openai_api_key,
    }
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    return OpenAI(**client_kwargs)


def generate_script_text(
    content_type: str,
    custom_topic: Optional[Dict[str, Any]],
    script_preferences: Optional[Dict[str, Any]],
    language_code: str = "en-US",
) -> str:
    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError(
            "OPENAI_API_KEY is not set. Add OPENAI_API_KEY=your_key to your .env file to enable script generation."
        )
    client = get_openai_client()
    prompt_parts = []
    content_type_map = {
        "motivation": "Create an inspiring motivational short-form video script",
        "horror": "Create a suspenseful horror story script",
        "finance": "Create an educational finance tip script",
        "ai_tech": "Create an engaging AI and technology explainer script",
        "kids": "Create a fun, educational script suitable for children",
        "anime": "Create an anime-style narrative script",
        "custom": "Create a custom content script",
    }
    base_prompt = content_type_map.get(content_type, "Create a video script")
    
    if content_type == "custom" and custom_topic:
        topic_title = custom_topic.get("topicTitle", "")
        target_audience = custom_topic.get("targetAudience", "")
        tone = custom_topic.get("tone", "")
        keywords = custom_topic.get("keywords", [])
        cta_style = custom_topic.get("ctaStyle", "")
        
        prompt_parts.append(f"{base_prompt} about: {topic_title}")
        if target_audience:
            prompt_parts.append(f"Target audience: {target_audience}")
        if tone:
            prompt_parts.append(f"Tone: {tone}")
        if keywords:
            prompt_parts.append(f"Keywords to include: {', '.join(keywords)}")
        if cta_style:
            prompt_parts.append(f"Call-to-action style: {cta_style}")
    else:
        prompt_parts.append(base_prompt)
    if script_preferences:
        story_length = script_preferences.get("storyLength", "30_40")
        if story_length == "30_40":
            prompt_parts.append("Length: 30-40 seconds of spoken content")
        elif story_length == "45_60":
            prompt_parts.append("Length: 45-60 seconds of spoken content")
        
        tone_pref = script_preferences.get("tone")
        if tone_pref:
            prompt_parts.append(f"Tone: {tone_pref}")
        
        hook_strength = script_preferences.get("hookStrength")
        if hook_strength:
            prompt_parts.append(f"Hook strength: {hook_strength}")
        
        include_cta = script_preferences.get("includeCta", False)
        cta_text = script_preferences.get("ctaText")
        if include_cta and cta_text:
            prompt_parts.append(f"Include call-to-action: {cta_text}")
    if language_code and language_code != "en-US":
        prompt_parts.append(f"Language: {language_code}")
    prompt_parts.append(
        "Write only the script text, no stage directions or notes. "
        "Make it engaging and suitable for a short-form video."
    )
    
    full_prompt = "\n".join(prompt_parts)
    
    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional scriptwriter for short-form video content. "
                    "Create engaging, concise scripts optimized for social media platforms.",
                },
                {"role": "user", "content": full_prompt},
            ],
            temperature=0.7,
            max_tokens=1000,
        )
        
        script_text = response.choices[0].message.content.strip()
        logger.info(f"Generated script (length: {len(script_text)} chars)")
        return script_text
        
    except Exception as e:
        logger.error(f"OpenAI API error: {e}", exc_info=True)
        raise ValueError(f"Failed to generate script: {str(e)}")


def generate_script_scenes(
    content_type: str,
    custom_topic: Optional[Dict[str, Any]],
    script_preferences: Optional[Dict[str, Any]],
    language_code: str = "en-US",
    num_scenes_min: int = 5,
    num_scenes_max: int = 12,
) -> List[SceneSpec]:
    settings = get_settings()
    if not settings.openai_api_key:
        raise ValueError(
            "OPENAI_API_KEY is not set. Add OPENAI_API_KEY=your_key to your .env file."
        )
    client = get_openai_client()
    content_type_map = {
        "motivation": "inspiring motivational short-form video",
        "horror": "suspenseful horror story",
        "finance": "educational finance tip",
        "ai_tech": "engaging AI and technology explainer",
        "kids": "fun, educational content for children",
        "anime": "anime-style narrative",
        "custom": "custom content",
    }
    theme = content_type_map.get(content_type, "short-form video")
    if content_type == "custom" and custom_topic:
        theme = f"custom: {custom_topic.get('topicTitle', theme)}"

    length_sec = "30-40"
    if script_preferences:
        sl = script_preferences.get("storyLength", "30_40")
        length_sec = "45-60" if sl == "45_60" else "30-40"

    system = (
        "You are a professional scriptwriter for short vertical videos (Reels/TikTok). "
        "Output ONLY a valid JSON array of scenes. No markdown, no code fence, no explanation."
    )
    user = (
        f"Create a {theme} script for {length_sec} seconds of spoken content. "
        f"Split it into exactly {num_scenes_min} to {num_scenes_max} short scenes. "
        "For each scene provide: "
        '"scene" (1-based index), '
        '"text" (the exact narration for that scene, one or two sentences), '
        '"visual_description" (short cinematic visual for that moment: setting, mood. MUST contain no text/letters/words/subtitles/signage/watermarks). '
        "Keep visual_description under 100 words, cinematic and concrete. "
        "Output a JSON array only, e.g. [{\"scene\":1,\"text\":\"...\",\"visual_description\":\"...\"}, ...]"
    )
    if language_code and language_code != "en-US":
        user += f" Language for narration: {language_code}."

    try:
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.6,
            max_tokens=2000,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = raw.rstrip("`").strip()
        data = json.loads(raw)
        scenes = validate_scenes(data)
        if len(scenes) > num_scenes_max:
            scenes = scenes[:num_scenes_max]
        logger.info("Generated %d scenes for scene-based pipeline", len(scenes))
        return scenes
    except json.JSONDecodeError as e:
        logger.warning("LLM returned invalid JSON: %s", e)
        raise ValueError("Script scenes response was not valid JSON") from e
    except Exception as e:
        logger.error("OpenAI API error in generate_script_scenes: %s", e, exc_info=True)
        raise ValueError(f"Failed to generate script scenes: {str(e)}") from e
