"""State and structured output for the profile agent.

``ProfileState`` **does** carry ``messages``, unlike ``VerifyState`` and
``PlanningState``. That is not an oversight: extracting "75kg, 4 days a week,
left knee hurts" from what the user typed is precisely a job that requires the
transcript. The isolation rule in ``docs/workflow.md`` §1.3 applies to agents
whose judgment must be independent of the conversation — the verifier and the
repairer — not to the one whose job is to read it.
"""

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

# The vocabularies downstream code matches on. An extraction outside these sets
# is silently dropped rather than stored, because `calc_macros` raises on an
# unknown activity level and `filter_candidates` would silently match nothing
# for an unknown equipment token.
Sex = ["male", "female"]
ACTIVITY_LEVELS = ["sedentary", "light", "moderate", "active", "very_active"]
GOALS = ["fat_loss", "muscle_gain", "recomp", "general_health"]


class ProfileExtraction(BaseModel):
    """Facts extracted from the conversation this turn.

    Every field is optional: a turn usually states one or two things, and the
    profile is accumulated across turns. ``None`` means "not mentioned", which
    must never overwrite a stored value.
    """

    weight_kg: float | None = Field(default=None, description="Body weight in kilograms")
    height_cm: float | None = Field(default=None, description="Height in centimetres")
    age: int | None = Field(default=None, description="Age in years")
    sex: str | None = Field(default=None, description="male or female")
    activity_level: str | None = Field(
        default=None,
        description="Daily life outside training: sedentary, light, moderate, active, very_active",
    )
    days_per_week: int | None = Field(default=None, description="Training sessions per week")
    level: int | None = Field(default=None, description="Training experience, 1 (new) to 5")
    goal: str | None = Field(
        default=None, description="fat_loss, muscle_gain, recomp or general_health"
    )
    equipment: list[str] | None = Field(
        default=None, description="Equipment tokens the user has access to"
    )
    injuries: list[str] | None = Field(
        default=None,
        description="Injury keys from the contraindication rubric. Empty list means none.",
    )
    preferences: str | None = Field(
        default=None, description="Exercises the user likes or wants to avoid, as free text"
    )
    unmapped_injury: str | None = Field(
        default=None,
        description=(
            "An injury the user described that is NOT one of the recognised keys, "
            "in their own words. Set this instead of guessing a key."
        ),
    )


class ProfileState(TypedDict):
    """Working state of the profile subgraph."""

    messages: Annotated[list, add_messages]
    user_id: int | None
    intent: str
    profile: dict
    missing_fields: list[str]
    # True when this turn learned something worth persisting.
    changed: bool
