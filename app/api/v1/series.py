"""Series wizard and launch endpoints."""

from uuid import UUID
from sqlalchemy import func
from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, CurrentWorkspace, DbSession
from app.schemas.series import (
    SeriesCreateBody,
    SeriesResponse,
    Step1ContentTypeUpdate,
    Step2ScriptPreferencesUpdate,
    Step3VoiceLanguageUpdate,
    Step4MusicUpdate,
    Step5ArtStyleUpdate,
    Step6CaptionStyleUpdate,
    Step7EffectsUpdate,
    Step8SocialUpdate,
    Step9ScheduleUpdate,
    LaunchSeriesResponse,
)
from app.services.series_service import (
    create_series,
    get_series,
    list_series,
    update_step_1,
    update_step_2,
    update_step_3,
    update_step_4,
    update_step_5,
    update_step_6,
    update_step_7,
    update_step_8,
    update_step_9,
    launch_series as do_launch_series,
)
from app.services.credits_service import estimate_credits_per_episode
from app.db.models.episode import Episode

router = APIRouter(prefix="/series", tags=["series"])


def _series_response(series):
    return SeriesResponse(
        id=series.id,
        workspaceId=series.workspace_id,
        name=series.name,
        contentType=series.content_type,
        customTopic=series.custom_topic,
        scriptPreferences=series.script_preferences,
        voiceLanguage=series.voice_language,
        musicSettings=series.music_settings,
        artStyle=series.art_style,
        captionStyle=series.caption_style,
        visualEffects=series.visual_effects,
        schedule=series.schedule,
        status=series.status,
        estimatedCreditsPerVideo=series.estimated_credits_per_video,
        autoPostEnabled=series.auto_post_enabled,
        connectedSocialAccountIds=series.connected_social_account_ids,
        createdAt=series.created_at.isoformat(),
        updatedAt=series.updated_at.isoformat(),
    )


def _require_series(db: DbSession, series_id: UUID, workspace_id: UUID):
    s = get_series(db, series_id, workspace_id)
    if not s:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Series not found")
    return s


@router.get("", response_model=list[SeriesResponse])
def series_list(
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    """List all series in the current workspace."""
    series_list_result = list_series(db, workspace.id)
    return [_series_response(s) for s in series_list_result]


@router.post("", response_model=SeriesResponse)
def series_create(
    body: SeriesCreateBody,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    series = create_series(
        db,
        workspace_id=workspace.id,
        name=body.name,
        content_type=body.contentType,
        custom_topic=body.customTopic.model_dump() if body.customTopic else None,
    )
    return _series_response(series)


@router.get("/{id}", response_model=SeriesResponse)
def series_get(
    id: UUID,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    series = _require_series(db, id, workspace.id)
    return _series_response(series)


@router.patch("/{id}/step/1-content-type", response_model=SeriesResponse)
def step_1(
    id: UUID,
    body: Step1ContentTypeUpdate,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    series = _require_series(db, id, workspace.id)
    update_step_1(
        db,
        series,
        name=body.name,
        content_type=body.contentType,
        custom_topic=body.customTopic.model_dump() if body.customTopic else None,
    )
    return _series_response(series)


@router.patch("/{id}/step/2-script-preferences", response_model=SeriesResponse)
def step_2(
    id: UUID,
    body: Step2ScriptPreferencesUpdate,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    series = _require_series(db, id, workspace.id)
    update_step_2(db, series, body.model_dump(exclude_none=True))
    return _series_response(series)


@router.patch("/{id}/step/3-voice-language", response_model=SeriesResponse)
def step_3(
    id: UUID,
    body: Step3VoiceLanguageUpdate,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    series = _require_series(db, id, workspace.id)
    update_step_3(db, series, body.model_dump(exclude_none=True))
    return _series_response(series)


@router.patch("/{id}/step/4-music", response_model=SeriesResponse)
def step_4(
    id: UUID,
    body: Step4MusicUpdate,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    series = _require_series(db, id, workspace.id)
    update_step_4(db, series, body.model_dump(exclude_none=True))
    return _series_response(series)


@router.patch("/{id}/step/5-art-style", response_model=SeriesResponse)
def step_5(
    id: UUID,
    body: Step5ArtStyleUpdate,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    series = _require_series(db, id, workspace.id)
    # Use by_alias=True so payload has artStyle, artIntensity (FE names) for storage
    payload = body.model_dump(exclude_none=True, by_alias=True)
    if body.colorTheme:
        payload["colorTheme"] = body.colorTheme.model_dump(exclude_none=True)
    update_step_5(db, series, payload)
    return _series_response(series)


@router.patch("/{id}/step/6-caption-style", response_model=SeriesResponse)
def step_6(
    id: UUID,
    body: Step6CaptionStyleUpdate,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    series = _require_series(db, id, workspace.id)
    update_step_6(db, series, body.model_dump(exclude_none=True))
    return _series_response(series)


@router.patch("/{id}/step/7-effects", response_model=SeriesResponse)
@router.patch("/{id}/step/7-visual-effects", response_model=SeriesResponse)  # Alias for FE compatibility
def step_7(
    id: UUID,
    body: Step7EffectsUpdate,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    """Step 7: Visual effects. Accepts both /step/7-effects and /step/7-visual-effects.
    
    Accepts either:
    - Array format: { "effects": [{ "type": "animatedHook", "enabled": false, ... }] }
    - Object format (FE): { "effects": { "animatedHook": { enabled, isPremium }, "filmGrain": { enabled }, ... } }
    - Or top-level keys: { "animatedHook": { enabled }, ... }
    """
    series = _require_series(db, id, workspace.id)

    def object_to_effects_array(obj):
        out = []
        for effect_name, effect_data in (obj or {}).items():
            if not isinstance(effect_data, dict):
                continue
            out.append({
                "type": effect_name,
                "enabled": effect_data.get("enabled", True),
                "isPremium": effect_data.get("isPremium", False),
                "params": effect_data.get("params"),
            })
        return out if out else None

    if body.effects is None:
        # Top-level effect keys (extra fields)
        body_dict = body.model_dump(exclude_none=True, exclude={"effects"})
        effects = object_to_effects_array(body_dict)
    elif isinstance(body.effects, list):
        effects = [e.model_dump() for e in body.effects]
    else:
        # effects is a dict (FE format: { effects: { animatedHook: {...}, filmGrain: {...} } })
        effects = object_to_effects_array(body.effects)

    update_step_7(db, series, effects)
    return _series_response(series)


@router.patch("/{id}/step/8-social", response_model=SeriesResponse)
@router.patch("/{id}/step/8-social-accounts", response_model=SeriesResponse)  # Alias for FE compatibility
def step_8(
    id: UUID,
    body: Step8SocialUpdate,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    """Step 8: Social accounts. Accepts both /step/8-social and /step/8-social-accounts. FE may send connectedAccountIds."""
    series = _require_series(db, id, workspace.id)
    ids = body.socialAccountIds if body.socialAccountIds is not None else body.connectedAccountIds
    update_step_8(db, series, ids)
    return _series_response(series)


@router.patch("/{id}/step/9-schedule", response_model=SeriesResponse)
def step_9(
    id: UUID,
    body: Step9ScheduleUpdate,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    series = _require_series(db, id, workspace.id)
    update_step_9(db, series, body.model_dump(exclude_none=True))
    return _series_response(series)


@router.post("/{id}/estimate-credits")
def estimate_credits(
    id: UUID,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    """Return credits estimate. FE expects { creditsPerEpisode, totalCredits, totalEpisodes }."""
    series = _require_series(db, id, workspace.id)
    credits_per_episode = estimate_credits_per_episode(series)
    total_episodes = db.query(func.count(Episode.id)).filter(Episode.series_id == id).scalar() or 0
    total_credits = credits_per_episode * total_episodes
    return {
        "creditsPerEpisode": credits_per_episode,
        "totalCredits": total_credits,
        "totalEpisodes": total_episodes,
        "perEpisode": credits_per_episode,
        "estimatedCreditsPerVideo": credits_per_episode,
    }


@router.post("/{id}/launch", response_model=LaunchSeriesResponse)
def launch(
    id: UUID,
    db: DbSession,
    user: CurrentUser,
    workspace: CurrentWorkspace,
):
    series = _require_series(db, id, workspace.id)
    try:
        series, upcoming, credit_estimate = do_launch_series(db, series, workspace)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return LaunchSeriesResponse(
        series=_series_response(series),
        upcomingEpisodes=upcoming,
        creditEstimate=credit_estimate,
    )
