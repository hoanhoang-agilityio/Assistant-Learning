"""Exercises as the training catalogue holds them.

These are read, never written by the agent: an exercise the coach agent prescribes has to
be one of these rows, which is what stops it inventing movements.
"""

from pydantic import BaseModel, Field

from src.enums import (
    BodyRegion,
    DifficultyLevel,
    EquipmentType,
    MovementPattern,
    MuscleGroup,
)


class ExerciseContraindication(BaseModel):
    """A condition under which an exercise must not be selected."""

    body_part: str = Field(description="Affected body part.")
    movement_patterns: list[MovementPattern] = Field(
        default_factory=list, description="Contraindicated movement patterns."
    )
    reason: str | None = Field(default=None)


class Exercise(BaseModel):
    """One movement in the training catalogue."""

    id: str = Field(description="Unique exercise identifier.")
    name: str = Field(description="Exercise name.")
    body_region: BodyRegion = Field(description="Primary body region targeted.")
    primary_muscles: list[MuscleGroup] = Field(
        min_length=1, description="Primary target muscles."
    )
    movement_pattern: MovementPattern = Field(description="Primary movement pattern.")
    difficulty: DifficultyLevel = Field(description="Experience the exercise assumes.")
    secondary_muscles: list[MuscleGroup] = Field(
        default_factory=list, description="Secondary target muscles."
    )
    equipment: list[EquipmentType] = Field(
        default_factory=list, description="Equipment required to perform it."
    )
    contraindications: list[ExerciseContraindication] = Field(
        default_factory=list, description="Injury contraindications."
    )
    description: str | None = Field(default=None)
    instructions: list[str] = Field(
        default_factory=list, description="Step-by-step instructions."
    )
    notes: str | None = Field(default=None)

    def is_contraindicated_for(self, body_part: str) -> bool:
        """Whether this exercise is ruled out for an injury to the given body part."""
        return any(
            contraindication.body_part.casefold() == body_part.casefold()
            and (
                not contraindication.movement_patterns
                or self.movement_pattern in contraindication.movement_patterns
            )
            for contraindication in self.contraindications
        )
