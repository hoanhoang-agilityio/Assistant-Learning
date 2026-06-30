"""Flatten and merge extracted profile models into orchestration profile dicts."""

from typing import Any

from core.profile.schema import ExtractedProfile

GYM_ACTIVITY_PREFIX = "gym_"
GYM_ACTIVITY_SUFFIX = "x_week"
MIN_TRAINING_DAYS = 1
MAX_TRAINING_DAYS = 6


def _round_measurement(value: float) -> float:
    return round(float(value), 1)


def _activity_level_from_days(days: int) -> str:
    if days == 0:
        return "sedentary"
    clamped = min(max(days, MIN_TRAINING_DAYS), MAX_TRAINING_DAYS)
    return f"gym_{clamped}x_week"


def _parse_gym_days_from_activity_level(activity_level: str) -> int | None:
    """Parse gym_Nx_week strings supplied via API user_profile (not LLM extraction)."""
    if not activity_level.startswith(GYM_ACTIVITY_PREFIX) or not activity_level.endswith(
        GYM_ACTIVITY_SUFFIX
    ):
        return None
    days_text = activity_level[len(GYM_ACTIVITY_PREFIX) : -len(GYM_ACTIVITY_SUFFIX)]
    if not days_text.isdigit():
        return None
    return min(max(int(days_text), MIN_TRAINING_DAYS), MAX_TRAINING_DAYS)


def normalize_extracted_profile(extracted: ExtractedProfile) -> dict[str, Any]:
    """Flatten nested extraction models into the flat profile dict used by planning."""
    profile: dict[str, Any] = {}
    biometrics = extracted.profile
    if biometrics.age is not None:
        profile["age"] = biometrics.age
    if biometrics.sex is not None:
        profile["sex"] = biometrics.sex
    if biometrics.height_cm is not None:
        profile["height_cm"] = _round_measurement(biometrics.height_cm)
    if biometrics.current_weight_kg is not None:
        profile["current_weight_kg"] = _round_measurement(biometrics.current_weight_kg)

    goal_info = extracted.goal
    if goal_info.goal is not None:
        profile["goal"] = goal_info.goal
    if goal_info.target_weight_kg is not None:
        profile["target_weight_kg"] = _round_measurement(goal_info.target_weight_kg)

    constraints = extracted.constraints
    if constraints.days_per_week is not None:
        days = int(constraints.days_per_week)
        profile["days_per_week"] = days
        profile["activity_level"] = _activity_level_from_days(days)
    if constraints.equipment is not None:
        profile["equipment"] = constraints.equipment
    if constraints.session_duration_minutes is not None:
        profile["session_duration_minutes"] = int(constraints.session_duration_minutes)
    if constraints.high_protein is not None:
        profile["high_protein"] = bool(constraints.high_protein)
    return profile


def _sync_activity_and_days(profile: dict[str, Any]) -> None:
    """Keep days_per_week and activity_level consistent after multi-source merge."""
    days = profile.get("days_per_week")
    if days is not None:
        days_int = int(days)
        profile["days_per_week"] = days_int
        profile["activity_level"] = _activity_level_from_days(days_int)
        return

    activity_level = profile.get("activity_level")
    if activity_level == "sedentary":
        profile["days_per_week"] = 0
        return
    if isinstance(activity_level, str):
        derived_days = _parse_gym_days_from_activity_level(activity_level)
        if derived_days is not None:
            profile["days_per_week"] = derived_days


def merge_profile_sources(
    *,
    query: str,
    user_profile: dict[str, Any],
    constraints: dict[str, Any],
    extracted: ExtractedProfile,
) -> dict[str, Any]:
    """Merge LLM extraction with constraints and existing user profile (profile wins)."""
    profile: dict[str, Any] = {"query": query}
    for field_name, value in constraints.items():
        if value is not None and value != "":
            profile[field_name] = value
    profile.update(normalize_extracted_profile(extracted))
    for field_name, value in user_profile.items():
        if field_name == "missing_fields":
            continue
        if value is not None and value != "":
            profile[field_name] = value
    _sync_activity_and_days(profile)
    return profile
