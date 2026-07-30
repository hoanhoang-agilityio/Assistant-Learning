"""Deterministic plan blueprint generation for the Fitness subgraph."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from core.shared.profile.goal_spec import GoalSpec


class PlanPhase(BaseModel):
    """A single prescription phase within a plan blueprint."""

    model_config = ConfigDict(extra="forbid")

    phase_index: int = Field(ge=1)
    week_start: int = Field(ge=1)
    week_end: int = Field(ge=1)
    name: str = Field(min_length=1)
    calorie_adjustment: int
    protein_g_per_kg: float = Field(gt=0)
    training_emphasis: str = Field(min_length=1)
    volume_modifier: float = Field(gt=0)


class PlanBlueprint(BaseModel):
    """Deterministic prescription blueprint derived from GoalSpec."""

    model_config = ConfigDict(extra="forbid")

    goal: str
    goal_archetype: str
    horizon_weeks: int | None = None
    weekly_rate_kg: float | None = None
    feasibility_level: str = "safe"
    template_family: str
    phases: list[PlanPhase]
    progression_notes: list[str] = Field(default_factory=list)


def _session_duration_bucket(minutes: int) -> str:
    if minutes <= 45:
        return "30-45"
    if minutes <= 60:
        return "45-60"
    return "60-90"


def _template_family(goal: str, days_per_week: int, equipment: str) -> str:
    return f"{goal}_{days_per_week}day_{equipment}"


def _build_phases(goal: str, horizon_weeks: int | None) -> list[PlanPhase]:
    total_weeks = horizon_weeks or 8
    phase_length = max(min(total_weeks // 2, 8), 4)
    phases: list[PlanPhase] = []
    week_start = 1
    phase_index = 1
    while week_start <= total_weeks:
        week_end = min(week_start + phase_length - 1, total_weeks)
        if goal == "fat_loss":
            emphasis = "metabolic"
            calorie_adjustment = -400
            protein = 2.0
            volume = 0.95 if phase_index > 1 else 1.0
        elif goal == "muscle_gain":
            emphasis = "hypertrophy"
            calorie_adjustment = 250
            protein = 2.2
            volume = 1.0 if phase_index == 1 else 1.05
        elif goal == "recomposition":
            emphasis = "mixed"
            calorie_adjustment = -150
            protein = 2.3
            volume = 1.0
        elif goal == "strength":
            emphasis = "strength"
            calorie_adjustment = 200
            protein = 2.0
            volume = 1.0
        elif goal == "endurance":
            emphasis = "metabolic"
            calorie_adjustment = 0
            protein = 1.8
            volume = 1.0
        else:
            emphasis = "mixed"
            calorie_adjustment = 0
            protein = 1.8
            volume = 1.0
        phases.append(
            PlanPhase(
                phase_index=phase_index,
                week_start=week_start,
                week_end=week_end,
                name=f"phase_{phase_index}",
                calorie_adjustment=calorie_adjustment,
                protein_g_per_kg=protein,
                training_emphasis=emphasis,
                volume_modifier=volume,
            )
        )
        week_start = week_end + 1
        phase_index += 1
    return phases


def build_plan_blueprint(
    profile: dict[str, Any],
    constraints: dict[str, Any],
    goal_spec: GoalSpec,
) -> PlanBlueprint:
    """Build a deterministic plan blueprint from profile, constraints, and GoalSpec.

    `goal_spec` must be derived by the caller from this same `profile` -- see the
    single-derivation threading rule in core/profile/goal_spec.py.
    """
    goal = str(profile.get("goal", "general_fitness"))
    days_per_week = int(profile.get("days_per_week") or constraints.get("days_per_week") or 3)
    equipment = str(constraints.get("equipment") or profile.get("equipment") or "gym")
    horizon_weeks = profile.get("horizon_weeks")
    if horizon_weeks is not None:
        horizon_weeks = int(horizon_weeks)
    progression_notes = [
        "Increase load or reps when all sets reach the top of the prescribed rep range.",
        "Use a deload if performance or recovery drops for two consecutive weeks.",
    ]
    if horizon_weeks:
        progression_notes.append(
            f"Program horizon is {horizon_weeks} weeks with phased volume and calorie targets."
        )
    return PlanBlueprint(
        goal=goal,
        goal_archetype=goal_spec.goal_archetype,
        horizon_weeks=horizon_weeks,
        weekly_rate_kg=goal_spec.weekly_rate_kg,
        feasibility_level=goal_spec.feasibility_level,
        template_family=_template_family(goal, days_per_week, equipment),
        phases=_build_phases(goal, horizon_weeks),
        progression_notes=progression_notes,
    )


def session_duration_bucket_from_profile(
    profile: dict[str, Any],
    constraints: dict[str, Any],
) -> str:
    minutes = int(
        constraints.get("session_duration_minutes") or profile.get("session_duration_minutes") or 60
    )
    return _session_duration_bucket(minutes)
