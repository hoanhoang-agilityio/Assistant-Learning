"""Everything the rules read, resolved once before any of them runs.

The rules need the template and the catalogue rows behind a plan, and all five need the
same ones. Fetching them here is what keeps the rules themselves pure and synchronous:
they take this object and return issues, with no database and nothing to await, which is
also what makes them testable from a literal.

Nothing is taken from graph state except the plan and the profile. The template and the
exercises are re-read from the catalogue rather than trusted from the agent's tool calls —
a gate that believed what it was checking would not be one.
"""

from dataclasses import dataclass

from src.schemas import Exercise, TrainingPlan, UserProfile, WorkoutTemplate
from src.services.catalogue import fetch_exercises_by_id, fetch_template


@dataclass(frozen=True)
class PlanContext:
    """A plan, the user it is for, and the catalogue rows it refers to."""

    plan: TrainingPlan
    profile: UserProfile
    template: WorkoutTemplate | None
    exercises: dict[str, Exercise]

    def exercise_for(self, exercise_id: str) -> Exercise | None:
        """The catalogue row a prescription names, or None when it names nothing real."""
        return self.exercises.get(exercise_id)


async def build_plan_context(plan: TrainingPlan, profile: UserProfile) -> PlanContext:
    """Resolve the template and the exercises a plan refers to."""

    template = await fetch_template(plan.template_id)
    exercises = await fetch_exercises_by_id(
        [exercise.exercise_id for exercise in plan.planned_exercises()]
    )

    return PlanContext(
        plan=plan, profile=profile, template=template, exercises=exercises
    )
