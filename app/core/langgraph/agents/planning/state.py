"""State for the planning agent, and the structured output its LLM node returns.

No ``messages`` field. The one thing the planner needs from the conversation is
the user's stated preferences ("I hate deadlifts"), and it receives those as an
extracted string rather than a transcript. That keeps the reason a particular
exercise was chosen traceable to a value in state instead of to something buried
in a message list, and it means the planner cannot be steered by anything the
user said that was not first extracted deliberately.
"""

from operator import add
from typing import Annotated, TypedDict

from pydantic import BaseModel, Field

from app.schemas.graph import Issue


class ExerciseChoice(BaseModel):
    """One slot filled with one exercise."""

    slot_id: str = Field(description="The slot being filled")
    exercise_id: str = Field(description="Chosen exercise, from that slot's candidate list")


class ExerciseChoices(BaseModel):
    """Structured output of ``choose_exercises``.

    A model, not free text: every choice is validated against the slot's
    candidate list before it reaches the plan, and a schema makes that check a
    lookup rather than a parse.
    """

    choices: list[ExerciseChoice] = Field(
        default_factory=list, description="One entry per slot, in any order"
    )


class PlanningState(TypedDict):
    """Working state of the planning subgraph."""

    profile: dict
    goal: str
    preferences: str
    catalog: dict

    template: dict | None
    # Template slots with a `candidates` list attached by filter_candidates.
    slots: list[dict]
    draft_plan: dict | None

    issues: Annotated[list[Issue], add]
