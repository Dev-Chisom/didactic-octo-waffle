"""Credit estimation and plan limits."""

from app.db.models.series import Series
from app.db.models.workspace import Workspace


def estimate_credits_per_episode(series: Series) -> float:
    """
    Compute per-episode credit consumption from series config.
    Factors: length, voice, art style, premium effects.
    """
    base = 10.0
    script_prefs = series.script_preferences or {}
    story_length = script_prefs.get("storyLength", "30_40")
    if story_length == "45_60":
        base += 5.0
    art_style = series.art_style or {}
    style = art_style.get("style", "minimal_text")
    if style in ("cinematic_ai", "anime"):
        base += 8.0
    elif style in ("realistic", "cartoon", "comic"):
        base += 4.0
    effects = series.visual_effects or []
    premium_count = sum(1 for e in effects if e.get("enabled") and e.get("isPremium"))
    base += premium_count * 5.0
    return round(base, 1)


def get_workspace_limits(workspace: Workspace) -> dict:
    """Return plan limits and flags for UI (canUseAnimatedHook, maxSocialAccounts, etc.)."""
    limits = workspace.limits or {}
    plan = workspace.plan or "free"
    return {
        "plan": plan,
        "limits": limits,
        "canUseAnimatedHook": plan in ("pro", "agency") and limits.get("canUseAnimatedHook", True),
        "maxSocialAccounts": limits.get("maxConnectedAccounts", 1),
        "maxPremiumEffectsPerVideo": limits.get("maxPremiumEffectsPerVideo", 0),
        "maxSeries": limits.get("maxSeries", 1),
    }
