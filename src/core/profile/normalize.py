"""Flatten and merge extracted profile models into orchestration profile dicts.

The flat profile dict is raw-inputs-only (see core/profile/schema.py): nothing derived
(weight_delta_kg, weekly_rate_kg, feasibility_level, goal_archetype, activity_level) is
ever written into it. `resolve_target_weight` and `_normalize_days_per_week` handle the
two one-way ingestion cases where a derived-looking signal (a delta phrase, an
activity_level string) arrives from an external source and must be folded into its raw
equivalent (target_weight_kg, days_per_week) once, at intake time, then discarded.
"""

from typing import Any

from core.profile.schema import CONSTRAINT_FIELDS, ExtractedProfile

GYM_ACTIVITY_PREFIX = "gym_"
GYM_ACTIVITY_SUFFIX = "x_week"
MIN_TRAINING_DAYS = 1
MAX_TRAINING_DAYS = 6
DEFAULT_ACTIVITY_LEVEL = "gym_3x_week"


def _round_measurement(value: float) -> float:
    return round(float(value), 1)


def _activity_level_from_days(days: int) -> str:
    if days == 0:
        return "sedentary"
    clamped = min(max(days, MIN_TRAINING_DAYS), MAX_TRAINING_DAYS)
    return f"gym_{clamped}x_week"


def resolve_activity_level(days_per_week: int | None) -> str:
    """Pure, on-demand derivation of the activity-level label from days_per_week.

    Never stored in `profile` -- call this wherever the label/multiplier is needed
    (e.g. `calculate_macros_data`) instead of reading a persisted `activity_level` field.
    """
    if days_per_week is None:
        return DEFAULT_ACTIVITY_LEVEL
    return _activity_level_from_days(int(days_per_week))


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
    """Flatten nested extraction models into the flat profile dict used by planning.

    `weight_delta_kg` is flattened through here as a transient signal only -- callers
    (`merge_profile_sources`) must resolve it into `target_weight_kg` via
    `resolve_target_weight` before it reaches a persisted profile.
    """
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
    if goal_info.weight_delta_kg is not None:
        profile["weight_delta_kg"] = _round_measurement(goal_info.weight_delta_kg)
    if goal_info.horizon_weeks is not None:
        profile["horizon_weeks"] = int(goal_info.horizon_weeks)

    constraints = extracted.constraints
    if constraints.days_per_week is not None:
        profile["days_per_week"] = int(constraints.days_per_week)
    if constraints.equipment is not None:
        profile["equipment"] = constraints.equipment
    if constraints.session_duration_minutes is not None:
        profile["session_duration_minutes"] = int(constraints.session_duration_minutes)
    if constraints.high_protein is not None:
        profile["high_protein"] = bool(constraints.high_protein)

    return profile


def resolve_target_weight(profile: dict[str, Any]) -> None:
    """Resolve a raw `weight_delta_kg` signal into `target_weight_kg`, then discard it.

    `weight_delta_kg` is never a profile field -- it only ever arrives transiently from
    LLM extraction (a delta phrase like "lose 5kg") or revision text. If `current_weight_kg`
    is already known and no explicit `target_weight_kg` was also given, resolve the delta
    into an absolute target once, here, at intake time. Otherwise the signal is simply
    dropped (matching prior behavior: without a known current weight there was never a way
    to derive a target from a delta either). `GoalSpec.weight_delta_kg` recomputes the delta
    fresh from `target_weight_kg`/`current_weight_kg` every time it's needed downstream.
    """
    weight_delta = profile.pop("weight_delta_kg", None)
    if weight_delta is None:
        return
    current_weight = profile.get("current_weight_kg")
    if current_weight is not None and profile.get("target_weight_kg") is None:
        profile["target_weight_kg"] = round(float(current_weight) + float(weight_delta), 1)


def _normalize_days_per_week(profile: dict[str, Any]) -> None:
    """Keep days_per_week authoritative after multi-source merge.

    One-way only: an incoming `activity_level` string (a legacy/API input channel) is
    parsed into `days_per_week` when that's the only signal present, but `activity_level`
    itself is always popped afterward -- it is never a persisted profile field. Use
    `resolve_activity_level(days_per_week)` wherever the label/multiplier is needed.
    """
    activity_level = profile.pop("activity_level", None)
    if profile.get("days_per_week") is not None:
        profile["days_per_week"] = int(profile["days_per_week"])
        return
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
    profile: dict[str, Any],
    extracted: ExtractedProfile,
) -> dict[str, Any]:
    """Merge LLM extraction with the stored/seed profile (stored profile wins).

    Preserves the original three-tier precedence even though the seed is now a single
    flat dict rather than separate `user_profile`/`constraints` arguments: constraint
    fields (`CONSTRAINT_FIELDS`) stay lowest priority (a fresh query can override a stale
    training-day/equipment preference), everything else in the seed profile stays highest
    priority (already-confirmed biometrics/goal fields must never be clobbered by a fresh
    partial extraction), with LLM `extracted` fields in between.
    """
    merged: dict[str, Any] = {"query": query}
    for field_name in CONSTRAINT_FIELDS:
        value = profile.get(field_name)
        if value is not None and value != "":
            merged[field_name] = value
    merged.update(normalize_extracted_profile(extracted))
    for field_name, value in profile.items():
        if field_name in CONSTRAINT_FIELDS or field_name == "missing_fields":
            continue
        if value is not None and value != "":
            merged[field_name] = value
    _normalize_days_per_week(merged)
    resolve_target_weight(merged)
    return merged
