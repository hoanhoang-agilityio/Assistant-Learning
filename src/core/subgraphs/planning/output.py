"""Public boundary schema for Planning capability outputs."""

from pydantic import BaseModel, ConfigDict, Field


class PlanningOutput(BaseModel):
    """Deterministic goal specification — no workouts or macros."""

    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=3)
    constraints: dict[str, str | int | float | bool] = Field(default_factory=dict)
    preferences: dict[str, str | int | float | bool] = Field(default_factory=dict)
    training_requirements: dict[str, str | int | float | bool] = Field(default_factory=dict)
    summary_markdown: str = Field(min_length=20)
