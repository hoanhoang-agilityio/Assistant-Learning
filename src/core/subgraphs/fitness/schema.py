"""Pydantic schemas for Fitness Planner structured outputs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    exercises: list[WorkoutExercise]

    @field_validator("exercises")
    @classmethod
    def validate_exercises(cls, exercises: list[WorkoutExercise]) -> list[WorkoutExercise]:
        if not exercises:
            raise ValueError("Each workout day must contain at least one exercise")
        return exercises


class StructuredWorkout(BaseModel):
    """LLM-generated structured workout plan."""

    model_config = ConfigDict(extra="forbid")

    split: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    days: list[WorkoutDay]
    weekly_sets: int = Field(ge=1)
    progression: str | None = None
    substitutions: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    evidence_applied: list[str] = Field(default_factory=list)

    @field_validator("days")
    @classmethod
    def validate_days(cls, days: list[WorkoutDay]) -> list[WorkoutDay]:
        if not days:
            raise ValueError("Structured workout must contain at least one training day")
        if len(days) > 6:
            raise ValueError("Structured workout must contain at most 6 training days")
        return days


class SafetyResult(BaseModel):
    """Deterministic safety validation result for a structured workout."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    feedback: list[str] = Field(default_factory=list)


class EditOperation(BaseModel):
    """Classification of a follow-up plan-edit request against an existing workout."""

    model_config = ConfigDict(extra="forbid")

    operation: Literal["ADD_DAY", "REMOVE_DAY", "REPLACE_EXERCISE", "UPDATE_MACROS", "OTHER"]
    target_exercise: str | None = None
    replacement_exercise: str | None = None
