"""Catalogue lookups behind the coach agent's tools."""

from sqlmodel import select

from src.models.catalogue import WorkoutTemplate as TemplateRow
from src.schemas import FitnessGoal, WorkoutTemplate
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
