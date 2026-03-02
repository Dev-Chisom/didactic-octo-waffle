from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from reel_engine.narration_llm import generate_narration_lines
from reel_engine.utils import clamp, pick_random, stable_hash_int


@dataclass(frozen=True)
class Shot:
    id: int
    duration_sec: float
    shot_type: str
    emotion: str
    camera_motion: str
    narration_text: str
    visual_beat: str


@dataclass(frozen=True)
class StoryPlan:
    style: str
    topic: str
    duration_sec: float
    shots: list[Shot]


# ---------------------------------------------------------------------------
# Arc label helper (used by both shot_specs builder and fallback)
# ---------------------------------------------------------------------------

def _arc_label(shot_index: int, num_shots: int) -> str:
    if shot_index == 0:
        return "hook"
    if num_shots <= 1:
        return "resolve"
    progress = shot_index / float(num_shots - 1)
    if progress < 0.20:
        return "setup"
    if progress < 0.45:
        return "build"
    if progress < 0.70:
        return "escalate"
    if progress < 0.85:
        return "twist"
    return "resolve"


# ---------------------------------------------------------------------------
# Topic keyword extraction
# ---------------------------------------------------------------------------

def _topic_keyword(topic: str) -> str:
    stop = {
        "the", "a", "an", "of", "in", "on", "at", "to", "for",
        "and", "or", "but", "with", "about", "this", "that", "it",
        "is", "was", "were", "are", "be", "been", "being",
    }
    words = re.findall(r"[A-Za-z']+", topic)
    meaningful = [w for w in words if w.lower() not in stop]
    keyword = " ".join(meaningful[:3]) if meaningful else topic[:20]
    return keyword.title()


# ---------------------------------------------------------------------------
# Main plan builder
# ---------------------------------------------------------------------------

def build_story_plan(
    *,
    style: str,
    topic: str,
    duration_sec: float,
    part_index: int = 1,
    parts_total: int = 1,
    cache_dir: Optional[Path] = None,
    previous_part_summary: Optional[str] = None,
) -> StoryPlan:
    """
    Lean shot planner designed for retention:
    - Strong hook in first ~2 seconds
    - Short early shots (faster pacing), slightly longer later shots
    - Each shot contains a 'visual_beat' to drive the image prompt
    - Narration generated via LLM; falls back to deterministic templates
    """
    duration_sec = clamp(float(duration_sec), 10, 600)
    part_index = max(1, int(part_index))
    parts_total = max(1, int(parts_total))
    if part_index > parts_total:
        part_index = parts_total

    if duration_sec <= 35:
        num_shots = 8
    elif duration_sec <= 50:
        num_shots = 10
    elif duration_sec <= 90:
        num_shots = 12
    else:
        target_shot_len = 12.0
        num_shots = int(round(duration_sec / target_shot_len))
        num_shots = int(clamp(num_shots, 14, 30))

    hook_dur = 2.0 if duration_sec <= 90 else 3.0
    remaining = max(1.0, duration_sec - hook_dur)
    base = remaining / (num_shots - 1)

    if duration_sec <= 90:
        min_d, max_d = 2.0, 7.0
    else:
        min_d, max_d = 5.0, 18.0

    durations = [hook_dur]
    for i in range(1, num_shots):
        w = (
            0.85 if i < max(3, int(num_shots * 0.20))
            else 1.10 if i > int(num_shots * 0.80)
            else 1.0
        )
        durations.append(clamp(base * w, min_d, max_d))

    scale = duration_sec / sum(durations)
    durations = [round(d * scale, 2) for d in durations]

    style_key = style.lower()
    part_label = f"Part {part_index}/{parts_total}" if parts_total > 1 else ""

    beats, emotions, shot_types, motions = _style_assets(style_key)

    # Build shot specs for LLM — include arc_position so pacing is respected
    shot_specs = [
        {
            "shot_id": i + 1,
            "visual_beat": beats[i % len(beats)],
            "emotion": emotions[i % len(emotions)],
            "arc_position": _arc_label(i, num_shots),
        }
        for i in range(num_shots)
    ]

    # Attempt LLM narration; fall back to topic-aware templates on any failure
    narration_lines = generate_narration_lines(
        style_key=style_key,
        topic=topic,
        shot_specs=shot_specs,
        part_index=part_index,
        parts_total=parts_total,
        part_label=part_label,
        cache_dir=cache_dir,
        previous_part_summary=previous_part_summary,
    )

    if not narration_lines or len(narration_lines) != num_shots:
        narration_lines = [
            _build_narration_line(
                style_key=style_key,
                topic=topic,
                part_index=part_index,
                parts_total=parts_total,
                shot_index=i,
                num_shots=num_shots,
                part_label=part_label,
                visual_beat=beats[i % len(beats)],
            )
            for i in range(num_shots)
        ]

    shots = [
        Shot(
            id=i + 1,
            duration_sec=durations[i],
            shot_type=shot_types[i % len(shot_types)],
            emotion=emotions[i % len(emotions)],
            camera_motion=motions[i % len(motions)],
            narration_text=narration_lines[i],
            visual_beat=beats[i % len(beats)],
        )
        for i in range(num_shots)
    ]

    return StoryPlan(style=style.lower(), topic=topic, duration_sec=duration_sec, shots=shots)


# ---------------------------------------------------------------------------
# Style asset definitions
# ---------------------------------------------------------------------------

def _style_assets(style_key: str) -> tuple[list, list, list, list]:
    if style_key == "crime":
        beats = [
            "evidence board close-up with photos and red string",
            "night street with police tape and flashing lights",
            "gloved hands placing an evidence bag on a table",
            "security camera view of an empty hallway",
            "interrogation room, chair and harsh overhead lamp",
            "archival newspaper headline about the case",
            "map with location pins and handwritten notes",
            "silhouette walking away in rain under streetlights",
            "file folder stamped CONFIDENTIAL",
            "wide shot of a quiet suburb at dusk",
            "close-up of a ticking clock, tension",
            "final reveal: empty evidence box, unanswered questions",
        ]
        emotions   = ["tense", "uneasy", "focused", "suspicious", "grave"]
        shot_types = ["close-up", "wide", "detail", "medium"]
        motions    = ["slow_push_in", "subtle_pan", "static"]

    elif style_key == "horror":
        beats = [
            "dark hallway with a door slightly ajar",
            "flickering light above stained walls",
            "close-up: dusty handprint on a mirror",
            "wide shot: empty bedroom with curtains moving",
            "shadow in the corner that shouldn't exist",
            "old tape recorder on a table, red light blinking",
            "basement stairs disappearing into darkness",
            "close-up: eye peeking through a crack",
            "foggy forest path at night",
            "flashlight beam catching something in frame",
            "door handle slowly turning by itself",
            "final: silhouette behind the viewer, almost unseen",
        ]
        emotions   = ["eerie", "dread", "tense", "paranoia", "panic"]
        shot_types = ["wide", "close-up", "detail", "medium"]
        motions    = ["slow_push_in", "static", "slow_tilt"]

    elif style_key == "cartoon":
        beats = [
            "cute hero character with a surprised expression",
            "bright town square, simple shapes",
            "mysterious package arrives with sparkle effects",
            "hero and sidekick exchange a look",
            "map pops open with animated icons",
            "funny chase scene silhouette",
            "hero solves a puzzle with colorful pieces",
            "big reveal: friendly creature appears",
            "celebration confetti and warm lighting",
            "end card: moral of the story",
            "hero waving goodbye",
            "teaser: next episode hint",
        ]
        emotions   = ["playful", "curious", "excited", "relieved", "happy"]
        shot_types = ["wide", "medium", "close-up"]
        motions    = ["gentle_zoom", "subtle_pan", "static"]

    elif style_key == "anime":
        beats = [
            "hero standing on a rooftop at dusk, city lights behind",
            "close-up on determined anime eyes with wind in hair",
            "mysterious glowing device in hero's hands",
            "best friend sidekick appears with energetic pose",
            "holographic map of the city lights up in the air",
            "quick action pose, cape or jacket flowing",
            "flashback-style frame with softer colors",
            "final heroic stance as the city glows below",
            "end card: stylized logo or symbol in the sky",
            "teaser: distant shadowed villain on another rooftop",
            "hero glancing back over shoulder, hair moving",
            "wide shot of the city with streaks of light",
        ]
        emotions   = ["determined", "curious", "excited", "hopeful", "brave"]
        shot_types = ["wide", "medium", "close-up"]
        motions    = ["gentle_zoom", "subtle_pan", "static"]

    else:  # faceless / default
        beats = [
            "hands typing on laptop in dim room",
            "coffee steam rising, morning routine",
            "city b-roll with shallow depth of field",
            "silhouette walking, backlit",
            "notebook with bullet points, aesthetic desk",
            "phone screen glow, scrolling",
            "close-up of sneakers on pavement",
            "sunset through window blinds",
            "hands opening a door, entering",
            "reflection in glass, faceless",
            "slow pan across minimalist room",
            "final: text-only vibe with clean background",
        ]
        emotions   = ["motivated", "focused", "calm", "aspirational"]
        shot_types = ["wide", "medium", "detail", "close-up"]
        motions    = ["gentle_zoom", "subtle_pan", "static"]

    return beats, emotions, shot_types, motions


# ---------------------------------------------------------------------------
# Fallback narration — topic-aware, visual-beat-connected, arc-driven
# ---------------------------------------------------------------------------

def _build_narration_line(
    *,
    style_key: str,
    topic: str,
    part_index: int,
    parts_total: int,
    shot_index: int,
    num_shots: int,
    part_label: str,
    visual_beat: str,
) -> str:
    seed = stable_hash_int(f"{style_key}::{topic}::p{part_index}::{shot_index}", bits=31)

    def choose(options: list[str]) -> str:
        return pick_random(options, seed=seed)

    kw   = _topic_keyword(topic)
    beat = visual_beat.split(",")[0].strip()

    arc  = _arc_label(shot_index, num_shots)
    is_final_part = part_index >= parts_total

    # ---- HORROR ----------------------------------------------------------
    if style_key == "horror":
        banks = {
            "hook": [
                f"You should not be watching this alone. This is about {kw}.",
                f"Nobody talks about {kw}. There's a reason for that.",
                f"The story of {kw} was buried fast. Too fast.",
                f"What you're about to see hasn't been explained. Ever.",
            ],
            "setup": [
                f"This is where {kw} began. It looked completely harmless.",
                f"The {beat} — that's the detail everyone missed with {kw}.",
                f"Every haunting has a first moment. For {kw}, it was this.",
                f"Most people ignored {kw}. The ones who didn't… changed.",
            ],
            "build": [
                f"The pattern in {kw} doesn't repeat by accident.",
                f"That {beat} appeared again. Three times in one night.",
                f"Investigators stopped logging {kw} after week two. Why?",
                f"Each report of {kw} described the same sound first.",
            ],
            "escalate": [
                f"Then {kw} stopped being a theory.",
                f"The {beat} — that wasn't supposed to move.",
                f"At this point in {kw}, the witnesses stopped talking.",
                f"Whatever {kw} is… it knew it was being watched.",
            ],
            "twist": [
                f"That's when {kw} turned inside out.",
                f"The {beat} was staged. Someone placed it there.",
                f"The real source of {kw} was in the room the whole time.",
                f"Nobody who investigated {kw} slept the same again.",
            ],
            "resolve": [
                f"Here's what {kw} actually was. Brace yourself.",
                f"The truth behind {kw} is worse than the story.",
                f"We found the answer to {kw}. You decide what to believe.",
            ],
        }
        recap = [
            f"Last time — {kw} showed us something we can't unsee.",
            f"Quick recap: {kw} got worse. Much worse.",
        ]
        cliff = [
            f"And then {kw} went silent. Completely silent.",
            f"The last piece of {kw} evidence disappeared overnight.",
            f"Someone deleted the {kw} file. We found a copy.",
        ]

    # ---- CRIME -----------------------------------------------------------
    elif style_key == "crime":
        banks = {
            "hook": [
                f"The {kw} case was closed in 72 hours. That was the first mistake.",
                f"Everyone believed the official story of {kw}. Almost everyone.",
                f"The {kw} file sat untouched for years. We opened it.",
                f"They said {kw} was solved. The evidence says otherwise.",
            ],
            "setup": [
                f"The {beat} — that's what investigators found first in {kw}.",
                f"In the {kw} case, the first clue was hiding in plain sight.",
                f"Every cold case has a crack. In {kw}, it was this.",
                f"The {kw} investigation started with a single discrepancy.",
            ],
            "build": [
                f"The {beat} in {kw} raised more questions than it answered.",
                f"Three details in {kw} never made it into the official report.",
                f"The pattern emerging from {kw} pointed somewhere unexpected.",
                f"Every witness in {kw} remembered this moment differently.",
            ],
            "escalate": [
                f"Then someone in the {kw} case changed their story.",
                f"The {beat} connected to {kw} in a way no one expected.",
                f"The {kw} trail went cold on purpose. Someone made sure of it.",
                f"At this stage in {kw}, the pressure from above was undeniable.",
            ],
            "twist": [
                f"Then the {kw} evidence turned completely.",
                f"The {beat} wasn't lost. It was removed.",
                f"The person who closed {kw} was in the room when it happened.",
                f"The real timeline of {kw} had been rewritten.",
            ],
            "resolve": [
                f"That's the full picture of {kw}. Draw your own conclusions.",
                f"The {kw} case finally connects — and it leads somewhere ugly.",
                f"Here's what the {kw} investigation actually found.",
            ],
        }
        recap = [
            f"Last time — {kw} gave us one lead we couldn't ignore.",
            f"Quick recap: {kw}. One witness. One lie. Everything unraveled.",
        ]
        cliff = [
            f"The final {kw} document vanished before the trial.",
            f"Then a name we recognized showed up in the {kw} file.",
            f"The {kw} case just… reopened. Quietly.",
        ]

    # ---- CARTOON ---------------------------------------------------------
    elif style_key == "cartoon":
        banks = {
            "hook": [
                f"Uh oh. Something weird is happening with {kw}.",
                f"Hold on — nobody told us {kw} could do THAT.",
                f"This is the story of {kw}. Buckle up.",
                f"One ordinary day. One {kw}. Everything changed.",
            ],
            "setup": [
                f"It all started when {kw} arrived out of nowhere.",
                f"The {beat} — that was the first clue about {kw}.",
                f"Nobody expected {kw} to be the answer. But here we are.",
                f"Every great adventure begins with a {beat}. This one has {kw}.",
            ],
            "build": [
                f"The clues about {kw} were adding up fast.",
                f"Our hero had a hunch about {kw}. And hunches don't lie.",
                f"The {beat} pointed straight at {kw}. Obviously.",
                f"Getting closer to {kw} meant things were about to get silly.",
            ],
            "escalate": [
                f"The {kw} puzzle got way harder. Like, a lot harder.",
                f"That {beat} was hiding the biggest secret about {kw}.",
                f"Nobody said solving {kw} would be easy. Nobody.",
                f"Three clues left. One answer. All roads lead to {kw}.",
            ],
            "twist": [
                f"Plot twist — {kw} was on our side the whole time!",
                f"Turns out the {beat} was a message from {kw}.",
                f"The {kw} mystery? It wasn't a mystery at all.",
                f"Surprise! {kw} wasn't the problem. We were.",
            ],
            "resolve": [
                f"And that's how {kw} taught our hero something important.",
                f"The {kw} adventure is over — and everyone went home happy.",
                f"Moral of the story: {kw} was never the problem. Fear was.",
            ],
        }
        recap = [
            f"Last time — {kw} got way more interesting.",
            f"Quick recap! {kw} surprised everyone. Even us.",
        ]
        cliff = [
            f"But wait — what's behind the {beat}? {kw} isn't done.",
            f"We thought {kw} was solved. We were wrong.",
            f"One more secret. And it's bigger than {kw}.",
        ]

    # ---- ANIME -----------------------------------------------------------
    elif style_key == "anime":
        banks = {
            "hook": [
                f"The night {kw} activated — nothing was the same.",
                f"I wasn't supposed to find {kw}. But I did.",
                f"Every hero has an origin. Mine started with {kw}.",
                f"They said {kw} was a myth. I'm standing proof it's not.",
            ],
            "setup": [
                f"The {beat} — that's where {kw} first appeared to me.",
                f"I had one night to understand {kw}. One night.",
                f"Every instinct said run. {kw} made me stay.",
                f"The city doesn't know about {kw}. I have to keep it that way.",
            ],
            "build": [
                f"Training for {kw} wasn't what I expected.",
                f"The {beat} confirmed what {kw} had been trying to show me.",
                f"My sidekick said {kw} was too dangerous. We went anyway.",
                f"Every step toward {kw} meant leaving something behind.",
            ],
            "escalate": [
                f"Then {kw} escalated. All at once.",
                f"The {beat} was a trap — and {kw} set it.",
                f"I had seconds to react. {kw} had been waiting for this.",
                f"The enemy knew about {kw}. That changed everything.",
            ],
            "twist": [
                f"Then the truth about {kw} hit like a shockwave.",
                f"The {beat} wasn't a weapon. It was a warning from {kw}.",
                f"The villain behind {kw} was someone I trusted.",
                f"I wasn't the first to find {kw}. My predecessor didn't survive.",
            ],
            "resolve": [
                f"We survived the night. {kw} made sure of that.",
                f"The {kw} mission is over. The war isn't.",
                f"Here's what I know now: {kw} chose me for a reason.",
            ],
        }
        recap = [
            f"Last time — {kw} revealed its true form.",
            f"Quick recap: {kw} chose me. I didn't choose it.",
        ]
        cliff = [
            f"And then {kw} went dark. Completely offline.",
            f"The rooftop wasn't empty. {kw} had sent someone.",
            f"We had one move left. {kw} made it for us.",
        ]

    # ---- FACELESS / DEFAULT ----------------------------------------------
    else:
        banks = {
            "hook": [
                f"I didn't believe {kw} would actually work. Then it did.",
                f"Most people quit before {kw} kicks in. Don't be most people.",
                f"The thing nobody tells you about {kw} — it starts invisible.",
                f"One decision about {kw} changed the next 90 days completely.",
            ],
            "setup": [
                f"The {beat} — that's what starting {kw} actually looks like.",
                f"Day one of {kw} looks like nothing. That's the point.",
                f"The system for {kw} is simpler than you think.",
                f"Most people overcomplicate {kw}. This is what it actually takes.",
            ],
            "build": [
                f"The {beat} is where {kw} starts to stick.",
                f"Week two of {kw} — the resistance hits hardest here.",
                f"Every boring day with {kw} is compounding in the background.",
                f"The {kw} routine doesn't feel like progress. Until it does.",
            ],
            "escalate": [
                f"Then {kw} started working in ways I didn't track.",
                f"The {beat} showed me {kw} was ahead of schedule.",
                f"Habits around {kw} started stacking without effort.",
                f"The hardest part of {kw} was already behind me.",
            ],
            "twist": [
                f"Then {kw} clicked. Not gradually — all at once.",
                f"The {beat} revealed the part of {kw} I'd been missing.",
                f"I stopped optimizing {kw} and it started optimizing me.",
                f"The {kw} system was working. I just needed to get out of the way.",
            ],
            "resolve": [
                f"Here's the full {kw} method. It's yours.",
                f"That's what {kw} taught me. Results speak louder.",
                f"The {kw} system works. Now you know where to start.",
            ],
        }
        recap = [
            f"Quick recap: {kw} started slow. Then it compounded.",
            f"Last time — {kw} showed the first real sign of progress.",
        ]
        cliff = [
            f"Then the old patterns came back. {kw} got tested.",
            f"One bad week and I almost abandoned {kw} entirely.",
            f"The {beat} reminded me why I started {kw} in the first place.",
        ]

    # ---- Position logic --------------------------------------------------
    if arc == "hook":
        line = choose(banks["hook"])
        if parts_total > 1:
            return f"{line} — {part_label}" if part_label else line
        return line

    # Recap line for part 2+ shot 1
    if parts_total > 1 and part_index > 1 and shot_index == 1:
        return choose(recap)

    # Cliffhanger for non-final parts ending
    if arc == "resolve" and parts_total > 1 and not is_final_part:
        return choose(cliff)

    return choose(banks.get(arc, banks["escalate"]))
