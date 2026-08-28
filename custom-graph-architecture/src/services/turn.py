"""What one turn said the user would rather, as distinct from what they are."""

from pydantic import BaseModel, Field


class PreferenceStatement(BaseModel):
    """What one turn said the user would rather, as distinct from what they are.

    Read in the same call as the profile fields because it is the same sentence that
    carries both — "I train 4 days, mornings, and I hate burpees" states one of each.
    """

    schedule: str | None = Field(
        default=None,
        description=(
            "When or how they prefer to train, in their own words, e.g. 'mornings', "
            "'sessions under 45 minutes'. Not how many days a week — that is a profile "
            "field."
        ),
    )
    liked_exercises: list[str] = Field(
        default_factory=list,
        description="Exercises or movements they said they enjoy or want more of.",
    )
    disliked_exercises: list[str] = Field(
        default_factory=list,
        description=(
            "Exercises or movements they said they dislike or want left out. A movement "
            "they cannot do because of pain is an injury, not a dislike."
        ),
    )
    diet: str | None = Field(
        default=None,
        description="Dietary preference, e.g. 'vegetarian', 'no dairy'.",
    )
    response_style: str | None = Field(
        default=None,
        description="How they want to be answered, e.g. 'keep it brief'.",
    )

    @property
    def is_empty(self) -> bool:
        """Whether the turn stated no preference at all, which is the usual case."""
        return not any(self.model_dump().values())
