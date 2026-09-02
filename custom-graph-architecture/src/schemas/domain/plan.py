"""The training plan the coach agent produces and the verification gate checks.

A prescription references a slot and a catalogue row by id and carries nothing else about
the exercise. Copying the name or the equipment onto it would let the agent state one
thing while ``exercise_id`` says another; anything the reader needs is resolved from the
catalogue at render time.
"""

from pydantic import BaseModel, Field

from src.enums import (
    BodyRegion,
    FitnessGoal,
)

KCAL_PER_GRAM_PROTEIN = 4
KCAL_PER_GRAM_CARBS = 4
KCAL_PER_GRAM_FAT = 9


class MacroTargets(BaseModel):
    """Daily macronutrient targets in grams."""

    protein_g: float = Field(ge=0, description="Daily protein target in grams.")
    carbs_g: float = Field(ge=0, description="Daily carbohydrate target in grams.")
    fat_g: float = Field(ge=0, description="Daily fat target in grams.")

    @property
    def calories(self) -> float:
        """The calories these macros come to, for the macro consistency check."""
        return (
            self.protein_g * KCAL_PER_GRAM_PROTEIN
            + self.carbs_g * KCAL_PER_GRAM_CARBS
            + self.fat_g * KCAL_PER_GRAM_FAT
        )


class NutritionTargets(BaseModel):
    """A profile's calorie and macro targets, as ``calc_macro`` hands them over."""

    goal: FitnessGoal = Field(description="The goal these targets were computed for.")
    bmr: int = Field(gt=0, description="Basal metabolic rate in kcal/day.")
    tdee: int = Field(gt=0, description="Maintenance calories in kcal/day.")
    daily_calories: int = Field(gt=0, description="Daily calorie target.")
    macros: MacroTargets = Field(description="Daily macro targets.")


class PlannedExercise(BaseModel):
    """One catalogue exercise, prescribed against the slot it was chosen to fill."""

    slot_id: str = Field(description="The template slot this exercise fills.")
    exercise_id: str = Field(
        description="Id of an exercise returned by the catalogue. Never invent one."
    )
    sets: int = Field(gt=0, description="Number of working sets.")
    reps: str = Field(description="Repetitions per set, e.g. '8-12' or '10'.")
    rest_seconds: int | None = Field(
        default=None, ge=0, description="Rest between sets."
    )
    notes: str | None = Field(default=None, description="Coaching notes, if any.")


class PlanDay(BaseModel):
    """One training day of the plan, filling one day of the template."""

    day_number: int = Field(ge=1, description="Day sequence number, starting at 1.")
    name: str = Field(description="Day name, e.g. 'Upper Push'.")
    exercises: list[PlannedExercise] = Field(
        min_length=1, description="Prescriptions for this day."
    )
    body_region: BodyRegion | None = Field(
        default=None, description="Primary region trained."
    )
    notes: str | None = Field(default=None)


class TrainingPlan(BaseModel):
    """A complete personalized training plan.

    The coach agent's structured output, and the object every deterministic verification
    rule is written against. ``template_id`` is what lets the gate re-resolve the slots
    the plan claims to fill.
    """

    template_id: str = Field(description="Id of the template this plan was built from.")
    goal: FitnessGoal = Field(description="The fitness goal this plan serves.")
    daily_calories: int = Field(gt=0, description="Daily calorie target.")
    macros: MacroTargets = Field(description="Daily macro targets.")
    training_days: list[PlanDay] = Field(
        min_length=1, description="The training week, in order."
    )
    summary: str | None = Field(
        default=None, description="Short description of the plan for the user."
    )
    notes: str | None = Field(default=None)

    def planned_exercises(self) -> list[PlannedExercise]:
        """Every prescription in the plan, across all of its days."""
        return [exercise for day in self.training_days for exercise in day.exercises]

    def filled_slot_ids(self) -> list[str]:
        """The slot each prescription claims to fill, duplicates included."""
        return [exercise.slot_id for exercise in self.planned_exercises()]


class PlanAnswer(BaseModel):
    """The coach's other shape of answer: a reply about the plan on record, not a new one.

    A turn that only asks what the stored plan holds has nothing for the verification gate
    to check and nothing for the user to approve. Returning this instead of a
    ``TrainingPlan`` is what tells the graph so.
    """

    answer: str = Field(
        description=(
            "The reply to show the user, drawn from what `get_plan` returned and "
            "nothing else."
        )
    )
