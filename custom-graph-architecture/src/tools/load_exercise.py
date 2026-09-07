"""``load_exercise``: the catalogue rows that can fill a template's slots."""

from typing import Any

from langchain.tools import ToolRuntime, tool
from pydantic import BaseModel, Field

from src.enums import (
    BodyRegion,
    MovementPattern,
    MuscleGroup,
)
from src.schemas import CoachContext
from src.services.catalogue import as_candidate, find_exercises
from src.tools.context import context_profile


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


@tool(response_format="content_and_artifact")
async def load_exercise(
    slots: list[SlotQuery], runtime: ToolRuntime[CoachContext, Any]
) -> tuple[dict, dict]:
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

    # The model only ever prescribes by id, choosing on the name; the movement pattern,
    # body region, muscles and equipment a candidate carries were already the query that
    # selected it, so repeating them back per slot would be paid for and never read.
    content = {
        slot_id: [
            {"id": exercise_id, "name": exercises[exercise_id]["name"]}
            for exercise_id in exercise_ids
        ]
        for slot_id, exercise_ids in by_slot.items()
    }
    return content, {"exercises": list(exercises.values()), "slots": by_slot}
