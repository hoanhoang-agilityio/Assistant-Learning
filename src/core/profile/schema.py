"""Pydantic schemas for fitness profile extraction and orchestration validation."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Sex = Literal["male", "female"]
FitnessGoal = Literal["fat_loss", "muscle_gain", "strength", "endurance", "general_fitness"]
ActivityLevel = Literal[
    "sedentary",
    "gym_1x_week",
    "gym_2x_week",
    "gym_3x_week",
    "gym_4x_week",
    "gym_5x_week",
    "gym_6x_week",
]
Equipment = Literal["gym", "home", "bodyweight"]

# Orchestration-level required fields (post-merge flat profile dict).
REQUIRED_PROFILE_FIELDS: tuple[str, ...] = (
    "age",
    "sex",
    "height_cm",
    "current_weight_kg",
    "activity_level",
    "goal",
)
GOAL_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "fat_loss": ("target_weight_kg",),
}
PROFILE_FIELDS: tuple[str, ...] = (
    "age",
    "sex",
    "height_cm",
    "current_weight_kg",
    "target_weight_kg",
    "activity_level",
    "goal",
)
CONSTRAINT_FIELDS: tuple[str, ...] = (
    "days_per_week",
    "equipment",
    "session_duration_minutes",
    "high_protein",
)


class Profile(BaseModel):
    """Biometric facts extracted from the user message.

    The LLM must convert imperial or relative measurements to these canonical SI fields
    before returning structured output.
    """

    model_config = ConfigDict(extra="forbid")

    age: int | None = Field(default=None, ge=13, le=100, description="Age in years")
    sex: Sex | None = Field(default=None, description="Biological sex")
    height_cm: float | None = Field(default=None, gt=0, le=250, description="Height in centimeters")
    current_weight_kg: float | None = Field(
        default=None, gt=0, le=300, description="Current body weight in kilograms"
    )


class Goal(BaseModel):
    """Fitness objective and goal-specific targets.

    Relative weight intents (e.g. "lose 2 kg") must be resolved by the LLM into
    ``target_weight_kg`` when current weight is known; otherwise leave null.
    """

    model_config = ConfigDict(extra="forbid")

    goal: FitnessGoal | None = Field(default=None, description="Primary fitness goal")
    target_weight_kg: float | None = Field(
        default=None,
        gt=0,
        le=300,
        description="Absolute target body weight in kilograms",
    )


class Constraints(BaseModel):
    """Training preferences that cannot be inferred from biometrics alone.

    ``activity_level`` is intentionally omitted; it is derived from ``days_per_week``
    during merge (0 = sedentary, 1–6 = gym_Nx_week).
    """

    model_config = ConfigDict(extra="forbid")

    days_per_week: int | None = Field(
        default=None,
        ge=0,
        le=6,
        description="Structured training days per week; use 0 when sedentary",
    )
    equipment: Equipment | None = Field(default=None, description="Available training equipment")
    session_duration_minutes: int | None = Field(
        default=None, ge=15, le=180, description="Preferred session length in minutes"
    )
    high_protein: bool | None = Field(
        default=None, description="Whether the user wants elevated protein intake"
    )


class ExtractedProfile(BaseModel):
    """Root schema for LLM structured extraction (OpenAI JSON Schema compatible)."""

    model_config = ConfigDict(extra="forbid")

    profile: Profile = Field(default_factory=Profile)
    goal: Goal = Field(default_factory=Goal)
    constraints: Constraints = Field(default_factory=Constraints)

    @field_validator("profile", "goal", "constraints", mode="before")
    @classmethod
    def coerce_null_nested_sections(cls, value: Any) -> Any:
        if value is None:
            return {}
        return value
