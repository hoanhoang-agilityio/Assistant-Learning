"""BMR / TDEE / macro-target arithmetic, and training-volume counting."""

import re
from typing import Any

from core.capabilities.fitness.constants import (
    ACTIVITY_MULTIPLIERS,
    DEFAULT_ACTIVITY_MULTIPLIER,
    MAX_CALORIES,
    MIN_CALORIES_FEMALE,
    MIN_CALORIES_MALE,
)
from core.shared.profile.goal_spec import GoalSpec, rate_to_calorie_adjustment
from core.shared.profile.normalize import resolve_activity_level


def _calculate_bmr(profile: dict[str, Any]) -> float:
    weight_kg = float(profile["current_weight_kg"])
    height_cm = float(profile["height_cm"])
    age = int(profile["age"])
    sex = str(profile.get("sex", "male")).lower()
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    if sex == "female":
        return base - 161
    return base + 5


def _activity_multiplier(activity_level: str) -> float:
    return ACTIVITY_MULTIPLIERS.get(activity_level, DEFAULT_ACTIVITY_MULTIPLIER)


def _minimum_calories(profile: dict[str, Any]) -> float:
    sex = str(profile.get("sex", "male")).lower()
    if sex == "female":
        return MIN_CALORIES_FEMALE
    return MIN_CALORIES_MALE


_REQUIRED_BIOMETRIC_FIELDS = ("current_weight_kg", "height_cm", "age")


def _has_required_biometrics(profile: dict[str, Any]) -> bool:
    return all(profile.get(field) is not None for field in _REQUIRED_BIOMETRIC_FIELDS)


def calculate_macros_data(
    profile: dict[str, Any],
    constraints: dict[str, Any],
    goal_spec: GoalSpec,
) -> dict[str, Any]:
    """`goal_spec` must be derived by the caller from this same `profile` -- see the
    single-derivation threading rule in core/profile/goal_spec.py.

    `macro_targets` is None when `profile` is missing weight/height/age (e.g. verify_plan,
    which has requires_profile=False) -- personalized calorie/macro math is meaningless
    without them, so this degrades gracefully instead of raising, matching how `goal`/
    `activity_level` above already default rather than requiring a complete profile.
    `training_constraints` never needs biometrics, so it's always computed.
    """
    goal = str(profile.get("goal", "general_fitness"))
    activity_level = resolve_activity_level(profile.get("days_per_week"))
    training_constraints = {
        "days_per_week": _parse_training_days(activity_level, constraints, profile),
        "session_duration_minutes": int(constraints.get("session_duration_minutes", 60)),
        "equipment": constraints.get("equipment", "gym"),
        "goal": goal,
    }
    if not _has_required_biometrics(profile):
        return {"macro_targets": None, "training_constraints": training_constraints}

    weight_kg = float(profile["current_weight_kg"])
    weekly_rate_kg = goal_spec.weekly_rate_kg

    bmr = _calculate_bmr(profile)
    tdee = bmr * _activity_multiplier(activity_level)
    calories = rate_to_calorie_adjustment(goal, tdee, weekly_rate_kg)
    calories = max(calories, _minimum_calories(profile))
    calories = min(calories, MAX_CALORIES)

    protein_grams_per_kg = 2.2 if goal in {"muscle_gain", "strength", "recomposition"} else 1.8
    if constraints.get("high_protein"):
        protein_grams_per_kg = 2.4
    if goal == "recomposition":
        protein_grams_per_kg = max(protein_grams_per_kg, 2.2)
    protein_g = round(weight_kg * protein_grams_per_kg)

    fat_calories = calories * 0.25
    fat_g = round(fat_calories / 9)
    carb_g = round(max((calories - (protein_g * 4) - (fat_g * 9)) / 4, 0))

    macro_targets = {
        "bmr": round(bmr),
        "tdee": round(tdee),
        "calories": round(calories),
        "protein_g": protein_g,
        "carbs_g": carb_g,
        "fat_g": fat_g,
        "goal": goal,
        "activity_level": activity_level,
    }
    return {
        "macro_targets": macro_targets,
        "training_constraints": training_constraints,
    }


def _parse_training_days(
    activity_level: str,
    constraints: dict[str, Any],
    profile: dict[str, Any],
) -> int:
    if profile.get("days_per_week") is not None:
        return int(profile["days_per_week"])
    if "days_per_week" in constraints:
        return int(constraints["days_per_week"])
    match = re.search(r"gym_(\d+)x_week", activity_level)
    if match:
        return int(match.group(1))
    return 3


def compute_weekly_sets(structured_workout: dict[str, Any]) -> int:
    """Sum exercise sets across all days in a structured workout."""
    return sum(
        int(exercise["sets"])
        for day in structured_workout.get("days", [])
        for exercise in day.get("exercises", [])
    )
