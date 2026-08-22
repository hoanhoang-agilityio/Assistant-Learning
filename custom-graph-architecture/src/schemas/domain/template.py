"""Workout templates: what a training week requires, before any exercise is chosen.

A template states requirements — "a horizontal push for chest" — and never names an
exercise. ``ExerciseSlot`` is both that requirement and the filter the catalogue is
queried with, so the catalogue can change without the template changing.
"""

from pydantic import BaseModel, Field

from src.schemas.domain.enums import BodyRegion, MovementPattern, MuscleGroup


class ExerciseSlot(BaseModel):
    """One exercise the training day needs, described by what it must satisfy."""

    slot_id: str = Field(description="Identifier for this slot within the template.")
    exercise_type: str | None = Field(
        default=None, description="Desired exercise type, in words."
    )
    target_muscles: list[MuscleGroup] = Field(
        default_factory=list, description="Muscle groups this slot has to train."
    )
    allowed_movement_patterns: list[MovementPattern] = Field(
        default_factory=list,
        description="Movement patterns that satisfy the slot. Empty means any.",
    )
    excluded_movement_patterns: list[MovementPattern] = Field(
        default_factory=list, description="Movement patterns that do not satisfy it."
    )
    required_body_region: BodyRegion | None = Field(
        default=None, description="Body region constraint, if any."
    )
    alternatives_allowed: bool = Field(
        default=True, description="Whether a substitute exercise may fill this slot."
    )
    notes: str | None = Field(default=None)

    def accepts_pattern(self, movement_pattern: MovementPattern) -> bool:
        """Whether a movement pattern satisfies this slot's constraints."""
        if movement_pattern in self.excluded_movement_patterns:
            return False
        if not self.allowed_movement_patterns:
            return True
        return movement_pattern in self.allowed_movement_patterns


class WorkoutDayTemplate(BaseModel):
    """The structure and constraints of one training day."""

    day_number: int = Field(ge=1, description="Day sequence number.")
    name: str = Field(description="Workout day name, e.g. 'Upper Push'.")
    body_region: BodyRegion = Field(description="Primary body region for the day.")
    exercise_slots: list[ExerciseSlot] = Field(
        min_length=1, description="Slots to fill, in order."
    )
    target_muscles: list[MuscleGroup] = Field(
        default_factory=list, description="Muscle groups the day should cover."
    )
    notes: str | None = Field(default=None)


class WorkoutTemplate(BaseModel):
    """A whole training week's structure, with no exercises chosen yet."""

    id: str = Field(description="Unique template identifier.")
    name: str = Field(description="Template name.")
    training_days: list[WorkoutDayTemplate] = Field(
        min_length=1, description="Training days, in order."
    )
    description: str | None = Field(default=None)
    notes: str | None = Field(default=None)

    def slots(self) -> list[ExerciseSlot]:
        """Every slot in the template, across all of its days."""
        return [slot for day in self.training_days for slot in day.exercise_slots]

    def slot_ids(self) -> set[str]:
        """The ids of every slot the template requires to be filled."""
        return {slot.slot_id for slot in self.slots()}
