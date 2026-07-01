"""Pydantic schemas for Fitness Planner structured outputs."""

from pydantic import BaseModel, ConfigDict, Field


class WorkoutExercise(BaseModel):
    """A single exercise prescription within a training day."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    sets: int = Field(ge=1, le=10)
    reps: str = Field(min_length=1)
    notes: str | None = None


class WorkoutDay(BaseModel):
    """One training day in the structured workout plan."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    focus: str = Field(min_length=1)
    exercises: list[WorkoutExercise] = Field(min_length=1)


class StructuredWorkout(BaseModel):
    """LLM-generated structured workout plan."""

    model_config = ConfigDict(extra="forbid")

    split: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    days: list[WorkoutDay] = Field(min_length=1, max_length=6)
    weekly_sets: int = Field(ge=1)
    progression: str | None = None
    substitutions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    evidence_applied: list[str] = Field(default_factory=list)


class SafetyResult(BaseModel):
    """Deterministic safety validation result for a structured workout."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    feedback: list[str] = Field(default_factory=list)
