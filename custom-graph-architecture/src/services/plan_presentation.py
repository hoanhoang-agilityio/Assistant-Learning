"""Rendering a verified ``TrainingPlan`` as markdown for the HITL review message."""

from src.schemas import Exercise, TrainingPlan
from src.services.catalogue import fetch_exercises_by_id


def _label(value: object) -> str:
    """Turn an enum's ``SCREAMING_SNAKE_CASE`` value into a display label."""

    return str(value).replace("_", " ").title()


def format_plan_markdown(plan: TrainingPlan, exercises: dict[str, Exercise]) -> str:
    """Render a plan's macros and training days as a markdown block."""

    macros = plan.macros
    lines = [
        f"**Goal:** {_label(plan.goal)}  ·  **Daily calories:** {plan.daily_calories} kcal",
        f"**Macros:** {macros.protein_g:g}g protein / {macros.carbs_g:g}g carbs / "
        f"{macros.fat_g:g}g fat",
        "",
    ]

    for day in plan.training_days:
        lines.append(f"**Day {day.day_number} — {day.name}**")
        for exercise in day.exercises:
            name = exercises[exercise.exercise_id].name
            rest = f" (rest {exercise.rest_seconds}s)" if exercise.rest_seconds else ""
            lines.append(f"- {name}: {exercise.sets} x {exercise.reps}{rest}")
        lines.append("")

    return "\n".join(lines).strip()


async def render_plan_markdown(plan: TrainingPlan) -> str:
    """Resolve the plan's exercises from the catalogue and render it as markdown."""

    exercises = await fetch_exercises_by_id(
        [exercise.exercise_id for exercise in plan.planned_exercises()]
    )
    return format_plan_markdown(plan, exercises)


__all__ = ["format_plan_markdown", "render_plan_markdown"]
