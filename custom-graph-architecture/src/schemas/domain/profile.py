"""The user: their injuries, their equipment and the profile the coach plans from."""

from pydantic import BaseModel, Field

from src.enums import (
    ActivityLevel,
    EquipmentType,
    FitnessGoal,
    InjuryStatus,
    MovementPattern,
    RestrictionAction,
    Sex,
)

MIN_AGE = 13
MAX_AGE = 100
MIN_TRAINING_DAYS = 1
MAX_TRAINING_DAYS = 7


class MovementRestriction(BaseModel):
    """A movement pattern an injury limits or rules out."""

    movement_pattern: MovementPattern = Field(description="Affected movement pattern.")
    action: RestrictionAction = Field(description="How hard the restriction is.")
    reason: str | None = Field(default=None, description="Why it applies.")


class Injury(BaseModel):
    """A current or previous injury and what it stops the user doing."""

    body_part: str = Field(description="Affected body part, e.g. shoulder, knee.")
    status: InjuryStatus = Field(
        default=InjuryStatus.ACTIVE, description="Whether it still constrains training."
    )
    severity: str | None = Field(default=None, description="Severity description.")
    restrictions: list[MovementRestriction] = Field(
        default_factory=list, description="Movement restrictions this injury causes."
    )
    notes: str | None = Field(default=None)

    @property
    def constrains_training(self) -> bool:
        """Whether this injury still limits exercise selection."""
        return self.status is not InjuryStatus.RESOLVED

    def prohibits(self, movement_pattern: MovementPattern) -> bool:
        """Whether this injury rules the movement pattern out entirely."""
        if not self.constrains_training:
            return False
        return any(
            restriction.movement_pattern is movement_pattern
            and restriction.action is RestrictionAction.PROHIBITED
            for restriction in self.restrictions
        )


class UserEquipment(BaseModel):
    """What the user can actually train with."""

    equipment: list[EquipmentType] = Field(
        default_factory=list, description="Available standard equipment."
    )
    other_equipment: list[str] = Field(
        default_factory=list, description="Additional or custom equipment."
    )

    def supports(self, required: list[EquipmentType]) -> bool:
        """Whether every piece of equipment an exercise needs is available."""
        return set(required) <= set(self.equipment)


class UserProfile(BaseModel):
    """Everything the coach agent needs to know about the user to build a plan.

    The fields without defaults are exactly the set the collection loop asks for:
    ``REQUIRED_PROFILE_FIELDS`` is derived from this model rather than restated.
    """

    age: int = Field(ge=MIN_AGE, le=MAX_AGE, description="Age in years.")
    sex: Sex = Field(description="Biological sex.")
    height_cm: float = Field(gt=0, description="Height in centimetres.")
    current_weight_kg: float = Field(gt=0, description="Current body weight in kg.")
    target_weight_kg: float | None = Field(
        default=None, gt=0, description="Goal body weight in kg."
    )
    activity_level: ActivityLevel = Field(description="Daily activity level.")
    goal: FitnessGoal = Field(description="Primary fitness goal.")
    training_days_per_week: int = Field(
        ge=MIN_TRAINING_DAYS,
        le=MAX_TRAINING_DAYS,
        description="Days per week the user can train.",
    )
    injuries: list[Injury] = Field(
        default_factory=list, description="Current or relevant previous injuries."
    )
    available_equipment: UserEquipment = Field(
        default_factory=UserEquipment, description="Equipment available to the user."
    )
    preferences: list[str] = Field(
        default_factory=list, description="Stated preferences, e.g. prefers dumbbells."
    )
    notes: str | None = Field(default=None)

    @property
    def active_injuries(self) -> list[Injury]:
        """The injuries that still constrain exercise selection."""
        return [injury for injury in self.injuries if injury.constrains_training]

    def prohibited_movements(self) -> set[MovementPattern]:
        """Every movement pattern an unresolved injury rules out."""
        return {
            restriction.movement_pattern
            for injury in self.active_injuries
            for restriction in injury.restrictions
            if restriction.action is RestrictionAction.PROHIBITED
        }
