"""``load_exercise``: the catalogue rows that can fill one template slot."""

from typing import Any

from langchain.tools import ToolRuntime, tool
from pydantic import ValidationError

from src.schemas import (
    BodyRegion,
    CoachContext,
    MovementPattern,
    MuscleGroup,
    UserProfile,
)
from src.services.catalogue import as_candidate, find_exercises


def context_profile(runtime: ToolRuntime[CoachContext, Any]) -> UserProfile | None:
    """The user's profile as the agent was invoked with it, or None when it is unusable."""

    context = runtime.context
    if not isinstance(context, CoachContext) or not context.profile:
        return None

    try:
        return UserProfile.model_validate(context.profile)
    except ValidationError:
        return None


@tool
async def load_exercise(
    movement_patterns: list[MovementPattern],
    runtime: ToolRuntime[CoachContext, Any],
    target_muscles: list[MuscleGroup] | None = None,
    body_region: BodyRegion | None = None,
    exclude_ids: list[str] | None = None,
) -> list[dict]:
    """Return exercises that can fill one template slot, already filtered by the user's injuries and equipment."""

    candidates = await find_exercises(
        context_profile(runtime),
        movement_patterns,
        target_muscles=target_muscles,
        body_region=body_region,
        exclude_ids=exclude_ids,
    )

    return [as_candidate(exercise) for exercise in candidates]
