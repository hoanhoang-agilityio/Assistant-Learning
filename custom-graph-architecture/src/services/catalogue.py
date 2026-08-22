"""Catalogue lookups behind the coach agent's tools."""

from sqlmodel import select

from src.models.catalogue import Exercise as ExerciseRow
from src.models.catalogue import WorkoutTemplate as TemplateRow
from src.schemas import (
    BodyRegion,
    DifficultyLevel,
    EquipmentType,
    Exercise,
    FitnessGoal,
    MovementPattern,
    MuscleGroup,
    UserEquipment,
    UserProfile,
    WorkoutTemplate,
)
from src.services.database import session_factory
from src.utils.logging import logger


def rank_templates(
    templates: list[WorkoutTemplate], days_per_week: int
) -> list[WorkoutTemplate]:
    """Order templates by how close they train to the requested week, most popular first."""

    return sorted(
        templates,
        key=lambda template: (
            abs(template.days_per_week - days_per_week),
            -template.popularity,
            template.id,
        ),
    )


async def fetch_templates(goal: FitnessGoal) -> list[WorkoutTemplate]:
    """Templates the goal is a reasonable choice for, or all of them when it has none."""

    async with session_factory() as session:
        statement = select(TemplateRow).where(
            TemplateRow.goals.contains([goal.value]))
        rows = (await session.execute(statement)).scalars().all()
        if not rows:
            rows = (await session.execute(select(TemplateRow))).scalars().all()

    return [row.to_schema() for row in rows]


async def find_template(
    goal: FitnessGoal, days_per_week: int
) -> WorkoutTemplate | None:
    """The template that best fits the goal and the days a week the user can train."""

    try:
        candidates = await fetch_templates(goal)
    except Exception as error:
        logger.exception("template_lookup_failed", goal=goal, error=str(error))
        return None

    ranked = rank_templates(candidates, days_per_week)
    return ranked[0] if ranked else None


MAX_EXERCISE_CANDIDATES = 8

# What the agent is handed per candidate. Instructions, contraindications and notes are
# left out: the agent picks a slot's exercise by id, and the rest would crowd the plan's
# context with a hundred rows it did not choose.
CANDIDATE_FIELDS = {
    "id",
    "name",
    "movement_pattern",
    "body_region",
    "primary_muscles",
    "secondary_muscles",
    "equipment",
    "difficulty",
}

# The tie-break when nothing else separates two candidates: the profile records no
# training experience, so the exercise that assumes the least is the safer default.
_DIFFICULTY_ORDER: dict[DifficultyLevel, int] = {
    DifficultyLevel.BEGINNER: 0,
    DifficultyLevel.INTERMEDIATE: 1,
    DifficultyLevel.ADVANCED: 2,
}


async def fetch_exercises(
    movement_patterns: list[MovementPattern],
    *,
    body_region: BodyRegion | None = None,
    exclude_ids: list[str] | None = None,
) -> list[Exercise]:
    """Catalogue rows matching a slot's pattern and region — what the indexes answer."""

    statement = select(ExerciseRow)
    if movement_patterns:
        statement = statement.where(
            ExerciseRow.movement_pattern.in_(list(movement_patterns))
        )
    if body_region is not None:
        statement = statement.where(ExerciseRow.body_region == body_region)
    if exclude_ids:
        statement = statement.where(ExerciseRow.id.not_in(list(exclude_ids)))

    async with session_factory() as session:
        rows = (await session.execute(statement)).scalars().all()

    return [row.to_schema() for row in rows]


def equipment_available(exercise: Exercise, equipment: UserEquipment) -> bool:
    """Whether the user can perform the exercise with what they have."""

    # An empty list is a profile nobody asked, not a user who owns nothing: equipment has
    # no default the collection loop fills in. Bodyweight is nobody's to own either.
    if not equipment.equipment:
        return True

    required = set(exercise.equipment) - {EquipmentType.BODYWEIGHT}
    return required <= set(equipment.equipment)


def allowed_exercises(
    exercises: list[Exercise], profile: UserProfile | None
) -> list[Exercise]:
    """Drop what the user's injuries rule out and what their equipment cannot support."""

    if profile is None:
        return list(exercises)

    prohibited = profile.prohibited_movements()
    injured_parts = {injury.body_part for injury in profile.active_injuries}

    return [
        exercise
        for exercise in exercises
        if exercise.movement_pattern not in prohibited
        and not any(exercise.is_contraindicated_for(part) for part in injured_parts)
        and equipment_available(exercise, profile.available_equipment)
    ]


def rank_exercises(
    exercises: list[Exercise], target_muscles: list[MuscleGroup]
) -> list[Exercise]:
    """Order by how directly an exercise trains the slot's muscles, easiest first."""

    # Muscles rank rather than filter: a slot is satisfied by its movement pattern, and a
    # slot whose muscles no catalogue row lists has to stay fillable.
    wanted = set(target_muscles)

    def _muscle_rank(exercise: Exercise) -> int:
        if not wanted or wanted & set(exercise.primary_muscles):
            return 0
        if wanted & set(exercise.secondary_muscles):
            return 1
        return 2

    return sorted(
        exercises,
        key=lambda exercise: (
            _muscle_rank(exercise),
            _DIFFICULTY_ORDER[exercise.difficulty],
            exercise.id,
        ),
    )


async def find_exercises(
    profile: UserProfile | None,
    movement_patterns: list[MovementPattern],
    *,
    target_muscles: list[MuscleGroup] | None = None,
    body_region: BodyRegion | None = None,
    exclude_ids: list[str] | None = None,
    limit: int = MAX_EXERCISE_CANDIDATES,
) -> list[Exercise]:
    """The exercises that can fill one template slot, best fit first."""

    try:
        candidates = await fetch_exercises(
            movement_patterns, body_region=body_region, exclude_ids=exclude_ids
        )
    except Exception as error:
        logger.exception("exercise_lookup_failed", error=str(error))
        return []

    permitted = allowed_exercises(candidates, profile)
    return rank_exercises(permitted, target_muscles or [])[:limit]


def as_candidate(exercise: Exercise) -> dict:
    """Render one exercise as the compact row the agent chooses from."""

    return exercise.model_dump(mode="json", include=CANDIDATE_FIELDS)
