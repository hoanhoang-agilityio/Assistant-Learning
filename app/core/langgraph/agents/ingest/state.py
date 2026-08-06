"""State and structured output for the ingest agent.

Carries ``messages`` because the plan being parsed *is* what the user typed.
Like the profile agent and unlike the verifier, reading the conversation is the
job.
"""

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class ParsedExercise(BaseModel):
    """One exercise line as the user wrote it."""

    raw_name: str = Field(description="Exercise name exactly as written, no interpretation")
    sets: int | None = Field(default=None, description="Number of sets, null if not stated")
    reps: list[int] | None = Field(
        default=None, description="[min, max] rep range. A single number becomes [n, n]."
    )
    rir: list[int] | None = Field(default=None, description="[min, max] RIR, null if not stated")


class ParsedDay(BaseModel):
    """One training day as the user wrote it."""

    name: str = Field(description="Day label, e.g. 'Push A' or 'Monday'")
    exercises: list[ParsedExercise] = Field(default_factory=list)


class ParsedPlan(BaseModel):
    """A pasted plan, normalised into structure but not yet into catalog ids."""

    days: list[ParsedDay] = Field(default_factory=list)
    is_a_plan: bool = Field(
        default=True,
        description="False when the message contains no training plan to assess",
    )


class IngestState(TypedDict):
    """Working state of the ingest subgraph."""

    messages: Annotated[list, add_messages]
    catalog: dict

    submitted_plan: dict | None
    # Exercise lines that could not be resolved confidently, each with the
    # candidates that were considered. Non-empty means the caller must ask.
    unresolved: list[dict]
    # Lines missing sets or reps: the volume check has nothing to count for them.
    incomplete: list[str]
