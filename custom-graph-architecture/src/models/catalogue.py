"""The training catalogue: the exercises and templates the coach agent may choose from.

Read-only at runtime. The coach agent can only prescribe rows that exist here, which is
what stops it inventing exercises; ``scripts/seed_catalogue.py`` is the only writer.

Exercises carry their filterable attributes as real columns because ``load_exercise``
queries on them. A template's days and slots are stored as one JSON document instead:
nothing ever queries a slot independently of the template it belongs to, so normalising
them into two more tables would add joins and buy nothing.
"""

from typing import Any

from sqlalchemy import Column, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from src.enums import (
    BodyRegion,
    DifficultyLevel,
    MovementPattern,
)
from src.schemas import (
    Exercise as ExerciseSchema,
)
from src.schemas import (
    WorkoutTemplate as WorkoutTemplateSchema,
)


def _jsonb() -> Column:
    """A JSONB column that defaults to an empty list rather than to NULL."""
    return Column(JSONB, nullable=False, server_default="[]")


class Exercise(SQLModel, table=True):
    """One movement in the catalogue."""

    __tablename__ = "exercise"
    __table_args__ = (
        Index("ix_exercise_pattern_region", "movement_pattern", "body_region"),
    )

    id: str = Field(primary_key=True)
    name: str = Field(index=True)
    movement_pattern: MovementPattern = Field(index=True)
    body_region: BodyRegion = Field(index=True)
    difficulty: DifficultyLevel = Field(index=True)
    primary_muscles: list[str] = Field(default_factory=list, sa_column=_jsonb())
    secondary_muscles: list[str] = Field(default_factory=list, sa_column=_jsonb())
    equipment: list[str] = Field(default_factory=list, sa_column=_jsonb())
    contraindications: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=_jsonb()
    )
    instructions: list[str] = Field(default_factory=list, sa_column=_jsonb())
    description: str | None = Field(default=None)
    notes: str | None = Field(default=None)

    def to_schema(self) -> ExerciseSchema:
        """Return the domain model the tools and the agent work with."""
        return ExerciseSchema.model_validate(self.model_dump())


class WorkoutTemplate(SQLModel, table=True):
    """One training week's structure, with no exercises chosen yet."""

    __tablename__ = "workout_template"

    id: str = Field(primary_key=True)
    name: str
    days_per_week: int = Field(index=True)
    popularity: int = Field(default=0)
    goals: list[str] = Field(default_factory=list, sa_column=_jsonb())
    training_days: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=_jsonb()
    )
    description: str | None = Field(default=None)
    notes: str | None = Field(default=None)

    def to_schema(self) -> WorkoutTemplateSchema:
        """Return the domain model the tools and the agent work with."""
        return WorkoutTemplateSchema.model_validate(self.model_dump())
