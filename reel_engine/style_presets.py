from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StylePreset:
    id: str
    display_name: str
    medium: str
    lighting: str
    lens: str
    color: str
    texture: str
    cinematic: str
    negative: str

    # Video/FFmpeg flavor knobs (lightweight, not a full grading system)
    eq_saturation: float
    eq_contrast: float
    eq_brightness: float
    grain_strength: float
    vignette: bool
    shake: bool


STYLE_PRESETS: dict[str, StylePreset] = {
    "crime": StylePreset(
        id="crime",
        display_name="Crime Documentary",
        medium="documentary-style cinematic photography, realistic, reenactment still",
        lighting="soft practical lighting, dim interior lights, overcast daylight, subtle shadows",
        lens="shot on 35mm and 50mm prime lens, shallow depth of field",
        color="desaturated, cool gray tones, muted teal shadows, low chroma",
        texture="fine film grain, archival texture, subtle halation",
        cinematic="crime documentary still, investigative tone, quiet tension, imperfect framing",
        negative=(
            "text, watermark, logo, subtitles, speech bubbles, cartoon, anime, lowres, blurry, "
            "deformed hands, extra fingers, distorted face, bad anatomy"
        ),
        eq_saturation=0.72,
        eq_contrast=1.10,
        eq_brightness=-0.02,
        grain_strength=0.12,
        vignette=True,
        shake=False,
    ),
    "horror": StylePreset(
        id="horror",
        display_name="Horror",
        medium="cinematic horror film still, realistic, atmospheric",
        lighting="low-key lighting, deep shadows, high contrast, single practical light, foggy ambience",
        lens="shot on 35mm wide angle and 85mm portrait lens, shallow depth of field",
        color="dark, high contrast, cold blue-green tint, desaturated",
        texture="heavy film grain, subtle motion blur, mist",
        cinematic="slow camera push-in, ambient dread, unsettling composition, suspense",
        negative=(
            "text, watermark, logo, subtitles, bright cheerful lighting, overexposed, "
            "cartoon, anime, lowres, blurry, deformed hands, extra fingers, distorted face"
        ),
        eq_saturation=0.62,
        eq_contrast=1.28,
        eq_brightness=-0.06,
        grain_strength=0.18,
        vignette=True,
        shake=True,
    ),
    "cartoon": StylePreset(
        id="cartoon",
        display_name="Cartoon Storytelling",
        medium="2D digital illustration, bold outlines, consistent line weight, clean shapes",
        lighting="soft studio lighting, gentle shading, no harsh shadows",
        lens="virtual camera 35mm lens, centered framing, clean perspective",
        color="controlled palette, vibrant but not neon, consistent colors",
        texture="clean, minimal grain, crisp edges",
        cinematic="animated movie still, readable silhouettes, playful emotion, simple background",
        negative=(
            "text, watermark, logo, subtitles, photorealistic, noisy, gritty, "
            "deformed hands, extra fingers, bad anatomy"
        ),
        eq_saturation=1.05,
        eq_contrast=1.05,
        eq_brightness=0.00,
        grain_strength=0.02,
        vignette=False,
        shake=False,
    ),
    "anime": StylePreset(
        id="anime",
        display_name="Anime Story Panel",
        medium="2D anime illustration, TV anime frame, clean cel shading, bold outlines",
        lighting="soft key light with gentle rim light, studio-style anime lighting",
        lens="virtual anime camera, 35mm lens equivalent, slight perspective",
        color="vibrant but controlled palette, pastel backgrounds, saturated accents",
        texture="very clean, minimal grain, crisp edges",
        cinematic="cinematic anime shot, dynamic posing, expressive faces, readable background",
        negative=(
            "text, watermark, logo, subtitles, photorealistic, noisy, gritty, painterly, watercolor, "
            "oil painting, lowres, blurry, deformed hands, extra fingers, bad anatomy, glitch"
        ),
        eq_saturation=1.08,
        eq_contrast=1.06,
        eq_brightness=0.01,
        grain_strength=0.01,
        vignette=False,
        shake=False,
    ),
    "faceless": StylePreset(
        id="faceless",
        display_name="Faceless B-Roll",
        medium="cinematic b-roll photography, lifestyle, moody",
        lighting="golden hour rim light or soft indoor practical light, pleasing shadows",
        lens="shot on 50mm prime lens, shallow depth of field, bokeh",
        color="slightly warm, high clarity, clean contrast",
        texture="subtle grain, clean image",
        cinematic="TikTok b-roll, smooth aesthetic, minimal subject detail, over-the-shoulder",
        negative=(
            "text, watermark, logo, subtitles, faces, identifiable person, "
            "deformed hands, extra fingers, bad anatomy, lowres, blurry"
        ),
        eq_saturation=1.10,
        eq_contrast=1.12,
        eq_brightness=0.01,
        grain_strength=0.06,
        vignette=False,
        shake=False,
    ),
}


def get_style_preset(style: str) -> StylePreset:
    key = style.strip().lower()
    if key not in STYLE_PRESETS:
        raise ValueError(f"Unknown style '{style}'. Choose one of: {', '.join(STYLE_PRESETS)}")
    return STYLE_PRESETS[key]

