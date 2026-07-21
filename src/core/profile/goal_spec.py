"""Goal specification helpers: derivation, feasibility, and archetype resolution."""

from typing import Any, Literal

FeasibilityLevel = Literal["safe", "aggressive", "unsafe"]

MAX_SAFE_FAT_LOSS_KG_PER_WEEK = 0.75
MAX_AGGRESSIVE_FAT_LOSS_KG_PER_WEEK = 1.0
MAX_SAFE_MUSCLE_GAIN_KG_PER_WEEK = 0.25
DEFAULT_RECOMP_HORIZON_WEEKS = 12
KCAL_PER_KG_FAT = 7700
KCAL_PER_KG_LEAN_MASS = 5500

WEIGHT_CHANGING_GOALS: frozenset[str] = frozenset({"fat_loss", "muscle_gain"})


def derive_goal_spec_fields(profile: dict[str, Any]) -> dict[str, Any]:
    """Derive weekly rate, target weight, and archetype from profile goal fields."""
    updates: dict[str, Any] = {}
    goal = profile.get("goal")
    current_weight = profile.get("current_weight_kg")
    weight_delta = profile.get("weight_delta_kg")
    target_weight = profile.get("target_weight_kg")
    horizon_weeks = profile.get("horizon_weeks")

    if current_weight is not None and weight_delta is not None and target_weight is None:
        updates["target_weight_kg"] = round(float(current_weight) + float(weight_delta), 1)
        target_weight = updates["target_weight_kg"]
    elif current_weight is not None and target_weight is not None and weight_delta is None:
        updates["weight_delta_kg"] = round(float(target_weight) - float(current_weight), 1)
        weight_delta = updates["weight_delta_kg"]

    if weight_delta is not None and horizon_weeks:
        weeks = max(int(horizon_weeks), 1)
        updates["weekly_rate_kg"] = round(abs(float(weight_delta)) / weeks, 3)

    if goal == "recomposition" and horizon_weeks is None:
        updates["horizon_weeks"] = DEFAULT_RECOMP_HORIZON_WEEKS

    merged = {**profile, **updates}
    feasibility = assess_goal_feasibility(merged)
    updates["feasibility_level"] = feasibility["level"]
    merged = {**profile, **updates}
    updates["goal_archetype"] = resolve_goal_archetype(merged)
    return updates


def resolve_goal_archetype(profile: dict[str, Any]) -> str:
    """Map profile goal fields to a planning/research archetype."""
    goal = str(profile.get("goal", "general_fitness"))
    feasibility = str(profile.get("feasibility_level", "safe"))
    horizon_weeks = profile.get("horizon_weeks")

    if goal == "fat_loss":
        if feasibility == "unsafe":
            return "fat_loss_aggressive_review_required"
        if feasibility == "aggressive":
            return "fat_loss_aggressive_review_required"
        return "fat_loss_moderate"
    if goal == "muscle_gain":
        return "muscle_gain_lean_bulk"
    if goal == "recomposition":
        return "recomposition"
    if goal == "strength":
        return "strength_focus"
    if goal == "endurance":
        if horizon_weeks:
            return "endurance_timeline_bound"
        return "endurance_timeline_bound"
    if goal == "maintenance":
        return "maintenance"
    return "general_fitness"


def assess_goal_feasibility(profile: dict[str, Any]) -> dict[str, Any]:
    """Assess whether the stated goal rate is safe, aggressive, or unsafe."""
    goal = profile.get("goal")
    weekly_rate = profile.get("weekly_rate_kg")
    weight_delta = profile.get("weight_delta_kg")
    issues: list[str] = []

    if goal in WEIGHT_CHANGING_GOALS and weight_delta is not None:
        delta = float(weight_delta)
        if goal == "fat_loss" and delta > 0:
            issues.append("goal_direction_conflict:fat_loss_positive_delta")
        if goal == "muscle_gain" and delta < 0:
            issues.append("goal_direction_conflict:muscle_gain_negative_delta")

    level: FeasibilityLevel = "safe"
    if weekly_rate is not None and goal == "fat_loss":
        rate = float(weekly_rate)
        if rate > MAX_AGGRESSIVE_FAT_LOSS_KG_PER_WEEK:
            level = "unsafe"
            issues.append("unrealistic_fat_loss_rate")
        elif rate > MAX_SAFE_FAT_LOSS_KG_PER_WEEK:
            level = "aggressive"
            issues.append("aggressive_fat_loss_rate")
    if weekly_rate is not None and goal == "muscle_gain":
        rate = float(weekly_rate)
        if rate > MAX_SAFE_MUSCLE_GAIN_KG_PER_WEEK * 2:
            level = "aggressive"
            issues.append("aggressive_muscle_gain_rate")

    requires_hitl = level == "unsafe" or any("goal_direction_conflict" in issue for issue in issues)
    return {
        "level": level,
        "issues": issues,
        "requires_hitl": requires_hitl,
        "message": _feasibility_message(level, issues),
    }


def _feasibility_message(level: FeasibilityLevel, issues: list[str]) -> str | None:
    if not issues:
        return None
    if "unrealistic_fat_loss_rate" in issues:
        return (
            "This target would require an unsafe rate of weight loss. "
            "A more realistic timeline would be significantly longer."
        )
    if any("goal_direction_conflict" in issue for issue in issues):
        return "Your stated goal conflicts with the target weight direction. Please clarify."
    if level == "aggressive":
        return "This goal is aggressive. Proceed only if you accept the associated risks."
    return None


def rate_to_calorie_adjustment(goal: str, tdee: float, weekly_rate_kg: float | None) -> float:
    """Convert weekly rate target into a daily calorie adjustment vs TDEE."""
    if weekly_rate_kg is None or weekly_rate_kg <= 0:
        return _default_calorie_adjustment(goal, tdee)
    if goal == "fat_loss":
        daily_deficit = (float(weekly_rate_kg) * KCAL_PER_KG_FAT) / 7
        return tdee - daily_deficit
    if goal == "muscle_gain":
        daily_surplus = (float(weekly_rate_kg) * KCAL_PER_KG_LEAN_MASS) / 7
        return tdee + daily_surplus
    if goal == "recomposition":
        return tdee - 150
    return _default_calorie_adjustment(goal, tdee)


def _default_calorie_adjustment(goal: str, tdee: float) -> float:
    if goal == "fat_loss":
        return tdee - 500
    if goal == "muscle_gain":
        return tdee + 300
    if goal == "strength":
        return tdee + 200
    if goal == "recomposition":
        return tdee - 150
    return tdee
