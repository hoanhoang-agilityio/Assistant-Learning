"""``load_exercise``: the catalogue rows that can fill a template's slots."""

from typing import Any

from langchain.tools import ToolRuntime, tool
from pydantic import BaseModel, Field

from src.core.langgraph.tools.context import context_profile
from src.schemas import BodyRegion, CoachContext, MovementPattern, MuscleGroup
from src.services.catalogue import as_candidate, find_exercises


class SlotQuery(BaseModel):
    """One template slot the agent needs candidates for."""

    slot_id: str = Field(description="The template slot these candidates are for.")
    movement_patterns: list[MovementPattern] = Field(
        description="Movement patterns that satisfy the slot."
    )
    target_muscles: list[MuscleGroup] | None = Field(
        default=None, description="Muscle groups the slot has to train."
    )
    body_region: BodyRegion | None = Field(
        default=None, description="Body region constraint, when the slot has one."
    )
    exclude_ids: list[str] | None = Field(
        default=None, description="Exercise ids already used elsewhere in the plan."
    )


@tool
async def load_exercise(
    slots: list[SlotQuery], runtime: ToolRuntime[CoachContext, Any]
) -> dict:
    """Return the exercises that can fill each template slot, already filtered by the user's injuries and equipment."""

    profile = context_profile(runtime)
    exercises: dict[str, dict] = {}
    by_slot: dict[str, list[str]] = {}

    for slot in slots:
        found = await find_exercises(
            profile,
            slot.movement_patterns,
            target_muscles=slot.target_muscles,
            body_region=slot.body_region,
            exclude_ids=slot.exclude_ids,
        )
        for exercise in found:
            exercises.setdefault(exercise.id, as_candidate(exercise))
        by_slot[slot.slot_id] = [exercise.id for exercise in found]

    return {"exercises": list(exercises.values()), "slots": by_slot}
