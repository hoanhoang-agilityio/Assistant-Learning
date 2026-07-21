"""Pydantic schemas for fitness profile extraction and orchestration validation."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Sex = Literal["male", "female"]
FitnessGoal = Literal[
    "fat_loss",
    "muscle_gain",
    "recomposition",
    "maintenance",
    "strength",
    "endurance",
    "general_fitness",
]
Equipment = Literal["gym", "home", "bodyweight"]
FeasibilityLevel = Literal["safe", "aggressive", "unsafe"]

# Orchestration-level required fields (post-merge flat profile dict).
#
# "goal" and "activity_level" are intentionally excluded: the onboarding form no longer
# collects them, and the downstream pipeline already degrades gracefully when they're
# absent (resolve_goal_archetype/calculate_macros_data default to "general_fitness" /
# "gym_3x_week"). Keeping them required here would make the profile_form HITL step
# pause forever, since nothing would ever supply them.
REQUIRED_PROFILE_FIELDS: tuple[str, ...] = (
    "age",
    "sex",
    "height_cm",
    "current_weight_kg",
    "target_weight_kg",
)
GOAL_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "fat_loss": (),
    "muscle_gain": (),
}
PROFILE_FIELDS: tuple[str, ...] = (
    "age",
    "sex",
    "height_cm",
    "current_weight_kg",
    "target_weight_kg",
    "weight_delta_kg",
    "horizon_weeks",
    "weekly_rate_kg",
    "goal_archetype",
    "feasibility_level",
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
    """Biometric facts extracted from the user message."""

    model_config = ConfigDict(extra="forbid")

    age: int | None = Field(default=None, ge=13, le=100, description="Age in years")
    sex: Sex | None = Field(default=None, description="Biological sex")
    height_cm: float | None = Field(default=None, gt=0, le=250, description="Height in centimeters")
    current_weight_kg: float | None = Field(
        default=None, gt=0, le=300, description="Current body weight in kilograms"
    )


class Goal(BaseModel):
    """Fitness objective and goal-specific targets."""

    model_config = ConfigDict(extra="forbid")

    goal: FitnessGoal | None = Field(default=None, description="Primary fitness goal")
    target_weight_kg: float | None = Field(
        default=None,
        gt=0,
        le=300,
        description="Absolute target body weight in kilograms",
    )
    weight_delta_kg: float | None = Field(
        default=None,
        ge=-100,
        le=100,
        description="Signed weight change in kilograms (negative=loss, positive=gain)",
    )
    horizon_weeks: int | None = Field(
        default=None,
        ge=1,
        le=260,
        description="Target timeline in weeks",
    )


class Constraints(BaseModel):
    """Training preferences that cannot be inferred from biometrics alone."""

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
