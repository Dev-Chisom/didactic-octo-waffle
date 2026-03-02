from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from reel_engine.story import StoryPlan


@dataclass(frozen=True)
class CaptionEvent:
    start: float
    end: float
    text: str


def build_caption_events(plan: StoryPlan) -> list[CaptionEvent]:
    """
    Simple timing: one caption per shot.
    This is intentionally cheap + deterministic and works well for 30–60s reels.
    """
    t = 0.0
    events: list[CaptionEvent] = []
    for shot in plan.shots:
        start = t
        end = t + float(shot.duration_sec)
        t = end
        text = _format_caption_text(shot.narration_text)
        events.append(CaptionEvent(start=start, end=end, text=text))
    return events


def burn_captions_into_frames(
    events: list[CaptionEvent],
    *,
    frame_paths: list[str],
    font_dir: Optional[str] = None,
) -> None:
    """
    Burn captions directly into the still frames.

    Why: Some FFmpeg builds (including yours) ship without libass and drawtext, so
    caption burn-in must happen pre-render.
    """
    from pathlib import Path

    from PIL import Image, ImageDraw, ImageFont

    if len(events) != len(frame_paths):
        raise ValueError("events must match frame_paths length")

    font_path = _pick_font_path(font_dir)

    for ev, fp in zip(events, frame_paths):
        path = Path(fp)
        im = Image.open(path).convert("RGBA")
        w, h = im.size

        # Scale font relative to image width (images are typically ~832px wide).
        font_size = max(22, int(round(w * 0.060)))
        font = _load_font(ImageFont=ImageFont, font_path=font_path, size=font_size)

        # Wrap text to fit.
        text = ev.text.replace("\\N", "\n").strip()
        wrapped = _wrap_text(text, font=font, max_width=int(w * 0.88))

        # Render in bottom-safe area.
        draw = ImageDraw.Draw(im)
        text_bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=6, align="center")
        text_w = text_bbox[2] - text_bbox[0]
        text_h = text_bbox[3] - text_bbox[1]

        x = int((w - text_w) / 2)
        y = int(h - (text_h + h * 0.14))

        # Box behind text (TikTok-friendly contrast).
        pad_x = int(w * 0.04)
        pad_y = int(h * 0.018)
        box = (
            max(0, x - pad_x),
            max(0, y - pad_y),
            min(w, x + text_w + pad_x),
            min(h, y + text_h + pad_y),
        )

        overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
        o = ImageDraw.Draw(overlay)
        o.rectangle(box, fill=(0, 0, 0, 170))
        im = Image.alpha_composite(im, overlay)

        draw = ImageDraw.Draw(im)

        # White text with black stroke if available.
        try:
            draw.multiline_text(
                (x, y),
                wrapped,
                font=font,
                fill=(255, 255, 255, 255),
                spacing=6,
                align="center",
                stroke_width=3,
                stroke_fill=(0, 0, 0, 255),
            )
        except TypeError:
            # Fallback: manual outline.
            for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, 2), (-2, 2), (2, -2)]:
                draw.multiline_text(
                    (x + dx, y + dy),
                    wrapped,
                    font=font,
                    fill=(0, 0, 0, 255),
                    spacing=6,
                    align="center",
                )
            draw.multiline_text(
                (x, y),
                wrapped,
                font=font,
                fill=(255, 255, 255, 255),
                spacing=6,
                align="center",
            )

        im.convert("RGB").save(path, format="PNG", optimize=True)


def write_ass(
    events: list[CaptionEvent],
    *,
    out_path: str,
    video_width: int,
    video_height: int,
    font_name: str = "Arial",
    font_size: int = 58,
) -> None:
    """
    Writes a minimal ASS subtitle file with a high-contrast boxed style.
    ASS gives more consistent styling across platforms than SRT + subtitles filter.
    """
    header = _ass_header(
        width=video_width,
        height=video_height,
        font_name=font_name,
        font_size=font_size,
    )
    lines = [header, "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    for ev in events:
        start = _ass_ts(ev.start)
        end = _ass_ts(ev.end)
        text = _ass_escape(ev.text)
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _format_caption_text(text: str) -> str:
    # Keep captions short and scannable. We also bias for 1–2 lines.
    text = text.strip()
    # Soft wrap: break on long text near the middle.
    if len(text) > 46 and " " in text:
        mid = len(text) // 2
        # find nearest space to mid
        left = text.rfind(" ", 0, mid)
        right = text.find(" ", mid)
        split_at = right if right != -1 and (right - mid) < (mid - left) else left
        if split_at > 0:
            text = text[:split_at].strip() + "\\N" + text[split_at + 1 :].strip()
    return text


def _pick_font_path(font_dir: Optional[str]) -> Optional[str]:
    # Prefer a user-provided font in assets/fonts, else try common system fonts.
    from pathlib import Path

    candidates: list[Path] = []
    if font_dir:
        d = Path(font_dir)
        if d.exists() and d.is_dir():
            for p in sorted(d.iterdir()):
                if p.suffix.lower() in {".ttf", ".otf"}:
                    candidates.append(p)
    if candidates:
        return str(candidates[0])

    system_candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttf",
    ]
    for p in system_candidates:
        if Path(p).exists():
            return p
    return None


def _load_font(*, ImageFont, font_path: str | None, size: int):
    if font_path:
        try:
            return ImageFont.truetype(font_path, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def _wrap_text(text: str, *, font, max_width: int) -> str:
    # Simple greedy wrap by words.
    words = text.replace("\n", " \n ").split()
    lines: list[str] = []
    cur: list[str] = []

    def line_width(s: str) -> int:
        # Pillow >=8 provides getlength; fallback to getbbox.
        if hasattr(font, "getlength"):
            return int(font.getlength(s))
        bbox = font.getbbox(s)
        return int(bbox[2] - bbox[0])

    for w in words:
        if w == "\n":
            if cur:
                lines.append(" ".join(cur))
                cur = []
            continue
        test = (" ".join(cur + [w])).strip()
        if test and line_width(test) <= max_width:
            cur.append(w)
        else:
            if cur:
                lines.append(" ".join(cur))
            cur = [w]
    if cur:
        lines.append(" ".join(cur))

    # Limit to 2 lines for retention; if more, compress by joining.
    if len(lines) > 2:
        # Merge extras into 2nd line.
        lines = [lines[0], " ".join(lines[1:])]
    return "\n".join(lines)


def _ass_header(*, width: int, height: int, font_name: str, font_size: int) -> str:
    # BorderStyle=3 draws an opaque box behind text (TikTok-friendly).
    # Alignment=2 means bottom-center.
    return "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {width}",
            f"PlayResY: {height}",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding",
            # White text, black outline, black box with slight transparency.
            "Style: Default,"
            f"{font_name},{font_size},"
            "&H00FFFFFF,&H000000FF,&H00101010,&H88000000,"
            "1,0,0,0,100,100,0,0,3,4,0,2,90,90,120,1",
            "",
        ]
    )


def _ass_escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", "\\N")
    )


def _ass_ts(seconds: float) -> str:
    # ASS timestamp: H:MM:SS.cs (centiseconds)
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s_int = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs == 100:
        cs = 0
        s_int += 1
    if s_int >= 60:
        s_int = 0
        m += 1
    if m >= 60:
        m = 0
        h += 1
    return f"{h}:{m:02d}:{s_int:02d}.{cs:02d}"

