"""Goal specification: derivation, feasibility, and archetype resolution.

`GoalSpec` is the single source of truth for every value computed from the raw
profile's goal fields (weight delta, weekly rate, feasibility, archetype, direction).
It is immutable and must be derived fresh -- via `derive_goal_spec` -- every time the
raw profile changes; nothing here is ever written back into the profile dict.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

FeasibilityLevel = Literal["safe", "aggressive", "unsafe"]
GoalDirection = Literal["loss", "gain", "maintain"]

MAX_SAFE_FAT_LOSS_KG_PER_WEEK = 0.75
MAX_AGGRESSIVE_FAT_LOSS_KG_PER_WEEK = 1.0
MAX_SAFE_MUSCLE_GAIN_KG_PER_WEEK = 0.25
DEFAULT_RECOMP_HORIZON_WEEKS = 12
KCAL_PER_KG_FAT = 7700
KCAL_PER_KG_LEAN_MASS = 5500

WEIGHT_CHANGING_GOALS: frozenset[str] = frozenset({"fat_loss", "muscle_gain"})


class GoalSpec(BaseModel):
    """Computed goal metrics derived from the raw profile. Immutable -- never mutate an
    existing instance; discard and call `derive_goal_spec` again once the raw profile
    changes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    goal: str | None = None
    weight_delta_kg: float | None = None
    weekly_rate_kg: float | None = None
    goal_direction: GoalDirection | None = None
    feasibility_level: FeasibilityLevel = "safe"
    feasibility_issues: list[str] = []
    feasibility_message: str | None = None
    goal_archetype: str = "general_fitness"

    @property
    def requires_hitl(self) -> bool:
        return self.feasibility_level == "unsafe" or any(
            "goal_direction_conflict" in issue for issue in self.feasibility_issues
        )


def derive_goal_spec(profile: dict[str, Any]) -> GoalSpec:
    """Derive weight delta, weekly rate, feasibility, and archetype from the raw profile.

    Computed entirely from raw fields (`current_weight_kg`, `target_weight_kg`, `goal`,
    `horizon_weeks`) every call -- there is no partial-update/memoization path, so the
    result can never go stale the way a cached derived field written into `profile` can.
    """
    goal = profile.get("goal")
    current_weight = profile.get("current_weight_kg")
    target_weight = profile.get("target_weight_kg")
    horizon_weeks = profile.get("horizon_weeks")

    weight_delta_kg: float | None = None
    if current_weight is not None and target_weight is not None:
        weight_delta_kg = round(float(target_weight) - float(current_weight), 1)

    effective_horizon_weeks = horizon_weeks
    if goal == "recomposition" and effective_horizon_weeks is None:
        effective_horizon_weeks = DEFAULT_RECOMP_HORIZON_WEEKS

    weekly_rate_kg: float | None = None
    if weight_delta_kg is not None and effective_horizon_weeks:
        weeks = max(int(effective_horizon_weeks), 1)
        weekly_rate_kg = round(abs(weight_delta_kg) / weeks, 3)

    goal_direction: GoalDirection | None = None
    if weight_delta_kg is not None:
        if weight_delta_kg > 0:
            goal_direction = "gain"
        elif weight_delta_kg < 0:
            goal_direction = "loss"
        else:
            goal_direction = "maintain"

    feasibility = assess_goal_feasibility(
        goal=goal, weight_delta_kg=weight_delta_kg, weekly_rate_kg=weekly_rate_kg
    )
    goal_archetype = resolve_goal_archetype(
        goal=goal, feasibility_level=feasibility["level"], horizon_weeks=horizon_weeks
    )

    return GoalSpec(
        goal=goal,
        weight_delta_kg=weight_delta_kg,
        weekly_rate_kg=weekly_rate_kg,
        goal_direction=goal_direction,
        feasibility_level=feasibility["level"],
        feasibility_issues=feasibility["issues"],
        feasibility_message=feasibility["message"],
        goal_archetype=goal_archetype,
    )


def resolve_goal_archetype(
    *,
    goal: str | None,
    feasibility_level: str,
    horizon_weeks: int | None,
) -> str:
    """Map goal + feasibility to a planning/research archetype."""
    goal = str(goal or "general_fitness")
    feasibility = str(feasibility_level or "safe")

    if goal == "fat_loss":
        if feasibility in ("unsafe", "aggressive"):
            return "fat_loss_aggressive_review_required"
        return "fat_loss_moderate"
    if goal == "muscle_gain":
        return "muscle_gain_lean_bulk"
    if goal == "recomposition":
        return "recomposition"
    if goal == "strength":
        return "strength_focus"
    if goal == "endurance":
        del horizon_weeks  # unused: both branches returned the same value historically
        return "endurance_timeline_bound"
    if goal == "maintenance":
        return "maintenance"
    return "general_fitness"


def assess_goal_feasibility(
    *,
    goal: str | None,
    weight_delta_kg: float | None,
    weekly_rate_kg: float | None,
) -> dict[str, Any]:
    """Assess whether the stated goal rate/direction is safe, aggressive, or unsafe."""
    issues: list[str] = []

    if goal in WEIGHT_CHANGING_GOALS and weight_delta_kg is not None:
        delta = float(weight_delta_kg)
        if goal == "fat_loss" and delta > 0:
            issues.append("goal_direction_conflict:fat_loss_positive_delta")
        if goal == "muscle_gain" and delta < 0:
            issues.append("goal_direction_conflict:muscle_gain_negative_delta")

    level: FeasibilityLevel = "safe"
    if weekly_rate_kg is not None and goal == "fat_loss":
        rate = float(weekly_rate_kg)
        if rate > MAX_AGGRESSIVE_FAT_LOSS_KG_PER_WEEK:
            level = "unsafe"
            issues.append("unrealistic_fat_loss_rate")
        elif rate > MAX_SAFE_FAT_LOSS_KG_PER_WEEK:
            level = "aggressive"
            issues.append("aggressive_fat_loss_rate")
    if weekly_rate_kg is not None and goal == "muscle_gain":
        rate = float(weekly_rate_kg)
        if rate > MAX_SAFE_MUSCLE_GAIN_KG_PER_WEEK * 2:
            level = "aggressive"
            issues.append("aggressive_muscle_gain_rate")

    return {
        "level": level,
        "issues": issues,
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
