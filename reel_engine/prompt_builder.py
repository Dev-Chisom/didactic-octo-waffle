from __future__ import annotations

from dataclasses import dataclass

from reel_engine.story import Shot, StoryPlan
from reel_engine.style_presets import StylePreset, get_style_preset
from reel_engine.utils import sha1_hex, stable_hash_int


@dataclass(frozen=True)
class ImagePrompt:
    shot_id: int
    prompt: str
    negative_prompt: str
    search_query: str
    seed: int
    width: int
    height: int
    steps: int
    guidance_scale: float
    cache_key: str


def seed_plan(*, style: str, topic: str, part_index: int = 1) -> int:
    # Deterministic base seed per reel/video part.
    part_index = max(1, int(part_index))
    return stable_hash_int(f"{style}::{topic}::part::{part_index}", bits=31)


def build_image_prompts(
    plan: StoryPlan,
    *,
    width: int,
    height: int,
    steps: int,
    guidance_scale: float,
    part_index: int = 1,
) -> tuple[StylePreset, int, list[ImagePrompt]]:
    preset = get_style_preset(plan.style)
    base_seed = seed_plan(style=plan.style, topic=plan.topic, part_index=part_index)

    prompts: list[ImagePrompt] = []
    for idx, shot in enumerate(plan.shots):
        seed = base_seed + idx
        text = _prompt_for_shot(preset=preset, shot=shot, topic=plan.topic)

        # Style-specific negative prompt boost to avoid painterly / blurry artifacts.
        style_key = plan.style.strip().lower()
        if style_key == "cartoon":
            extra_negative = (
                "blurry, low quality, oversaturated colors, neon lighting, distorted face, "
                "deformed anatomy, extra fingers, extra limbs, warped proportions, "
                "overexposed, underexposed, glowing skin, plastic skin, "
                "abstract, painterly, watercolor, oil painting, glitch, "
                "text, watermark, logo"
            )
            neg = f"{preset.negative}, {extra_negative}"
        elif style_key in {"horror", "crime"}:
            extra_negative = (
                "blurry, painterly, watercolor, oil painting, smeared, abstract, noisy, glitch, "
                "oversaturated colors"
            )
            neg = f"{preset.negative}, {extra_negative}"
        else:
            neg = preset.negative
        search_query = _search_query_for_shot(style=plan.style, shot=shot, topic=plan.topic)
        # Clamp steps for safety with various SDXL variants (most accept up to 50 comfortably).
        safe_steps = max(1, min(int(steps), 50))
        cache_key = sha1_hex(
            f"{plan.style}::{width}x{height}::{safe_steps}::{guidance_scale}::{seed}::{text}::{neg}"
        )

        prompts.append(
            ImagePrompt(
                shot_id=shot.id,
                prompt=text,
                negative_prompt=neg,
                search_query=search_query,
                seed=seed,
                width=width,
                height=height,
                steps=safe_steps,
                guidance_scale=guidance_scale,
                cache_key=cache_key,
            )
        )

    return preset, base_seed, prompts


def _prompt_for_shot(*, preset: StylePreset, shot: Shot, topic: str) -> str:
    subject_action = shot.visual_beat
    environment = f"theme: {topic}"
    emotion = shot.emotion
    motion_hint = _motion_hint(shot.camera_motion)
    shot_type_hint = _shot_type_hint(shot.shot_type)
    scene = f"{subject_action}, {environment}, {shot_type_hint}, {motion_hint}"

    style_id = preset.id.strip().lower()
    character = _character_description(style_id=style_id)

    # Style-specific production-grade templates tuned for graphic-novel look.
    if style_id == "horror":
        return (
            "dark cinematic horror illustration, graphic novel style, semi-realistic cartoon, "
            "clean sharp digital line art, dramatic shadows, moody lighting, eerie atmosphere, "
            "muted color palette, subtle film grain, "
            f"{scene}, unsettling mood, suspenseful tension, emotional tone: {emotion}, "
            f"main character: {character}, consistent design across all scenes, "
            "cinematic framing, dramatic rim lighting, high contrast shadows, shallow depth of field, "
            "high detail, sharp focus, clean composition, no distortion, no text"
        )

    if style_id == "cartoon":
        return (
            "cinematic comic book panel, clean sharp line art, modern animation style, "
            "consistent character design, realistic proportions, natural skin tones, balanced lighting, "
            "medium shot, centered character, soft shadow, subtle color grading, "
            "no distortion, no neon glow, no oversaturation, no text, "
            f"{scene}, playful but dramatic tone, emotional tone: {emotion}, "
            f"main character: {character}, detailed outfit and hairstyle, "
            "dynamic composition, readable background"
        )

    if style_id == "crime":
        return (
            "cinematic crime illustration, semi-realistic graphic novel style, "
            "clean digital line art, smooth shading, realistic facial expressions, "
            "muted color grading, subtle film grain, "
            f"{scene}, tense investigative atmosphere, emotional tone: {emotion}, "
            f"main character: {character}, consistent proportions and facial features, "
            "cinematic framing, dramatic side lighting, realistic depth of field, "
            "high detail, sharp focus, clean composition, no distortion, no text"
        )

    if style_id == "anime":
        return (
            "anime illustration, modern TV anime style, clean cel shading, bold outlines, "
            "large expressive eyes, dynamic hair, smooth gradients, crisp details, "
            f"{scene}, emotional tone: {emotion}, "
            f"main character: {character}, consistent outfit and hairstyle in every scene, "
            "cinematic anime frame, medium shot, slight low angle, dynamic pose, "
            "soft studio lighting with gentle rim light, "
            "sharp focus, clean line art, no blur, no painterly texture, no text"
        )

    # Faceless / fallback style.
    return (
        f"{scene}, {preset.medium}, {preset.lighting}, {preset.lens}, {preset.color}, "
        f"{preset.texture}, emotional tone: {emotion}, {preset.cinematic}, "
        "high detail, crisp focus, clean composition, no text"
    )


def _motion_hint(motion: str) -> str:
    motion = motion.strip().lower()
    if motion in {"slow_push_in", "gentle_zoom"}:
        return "implied slow camera push-in"
    if motion in {"subtle_pan"}:
        return "implied subtle camera pan"
    if motion in {"slow_tilt"}:
        return "implied slow camera tilt"
    return "static frame"


def _shot_type_hint(shot_type: str) -> str:
    t = shot_type.strip().lower()
    if t in {"close-up", "closeup"}:
        return "close-up shot"
    if t in {"wide"}:
        return "wide shot"
    if t in {"detail"}:
        return "detail shot"
    return "medium shot"


def _character_description(*, style_id: str) -> str:
    s = style_id.strip().lower()
    if s == "horror":
        return "pale clown with red hair, vintage 1960s costume, exaggerated unsettling smile, thin body, dark eye circles"
    if s == "cartoon":
        return (
            "8-year-old adventurous kid, small build, light brown skin, large round hazel eyes, "
            "oval face, shoulder-length dark brown hair in a loose ponytail, "
            "bright yellow raincoat over a blue hoodie, dark jeans, red sneakers"
        )
    if s == "crime":
        return "middle-aged detective in a grey suit, tired eyes, short dark hair, light stubble"
    if s == "anime":
        return (
            "11-year-old anime hero, slim build, light brown skin, big teal eyes, short spiky dark blue hair, "
            "white and teal tech jacket with glowing trim, black cargo shorts, knee-high socks, "
            "red high-top sneakers, fingerless gloves"
        )
    # Faceless / default.
    return "anonymous figure seen from behind, no visible facial features"


def _search_query_for_shot(*, style: str, shot: Shot, topic: str) -> str:
    """
    A short stock-footage-like query for providers (e.g., Pexels).

    Keep it short, visual, and avoid punctuation-heavy prompt strings.
    """
    base = shot.visual_beat
    if style == "crime":
        return f"{base}, crime investigation, documentary"
    if style == "horror":
        return f"{base}, dark, eerie, horror"
    if style == "cartoon":
        return f"{base}, cartoon, illustration"
    return f"{base}, cinematic b-roll, faceless"

