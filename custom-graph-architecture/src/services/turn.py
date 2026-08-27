"""One structured read of a user's turn: where it routes, and what it says about the user."""

from functools import lru_cache
from typing import Literal, get_args

from langchain_core.runnables import Runnable
from pydantic import BaseModel, Field

from src.core.langgraph.prompts import build_turn_parser_messages
from src.core.llm import chat_model, with_retry_policy
from src.enums import (
    ActivityLevel,
    FitnessGoal,
    InjuryStatus,
    Intent,
    Sex,
)
from src.utils.logging import logger

DEFAULT_INTENT: Intent = Intent.QA

FieldName = Literal[
    "age",
    "sex",
    "height_cm",
    "current_weight_kg",
    "target_weight_kg",
    "activity_level",
    "goal",
    "training_days_per_week",
]
EXTRACTABLE_FIELDS: tuple[str, ...] = get_args(FieldName)


class InjuryStatement(BaseModel):
    """An injury the user reported, without the movement restrictions it implies."""

    body_part: str = Field(description="Affected body part, e.g. shoulder, knee.")
    status: InjuryStatus = Field(
        default=InjuryStatus.ACTIVE, description="Whether it still constrains training."
    )
    severity: str | None = Field(
        default=None, description="Severity, in the user's words."
    )
    notes: str | None = Field(default=None)


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


class ProfileStatement(BaseModel):
    """What one turn said about the user, before it is merged into their profile."""

    age: int | None = Field(default=None, description="Age in years.")
    sex: Sex | None = Field(default=None)
    height_cm: float | None = Field(default=None, description="Height in centimetres.")
    current_weight_kg: float | None = Field(default=None, description="Weight in kg.")
    target_weight_kg: float | None = Field(
        default=None, description="Goal weight in kg."
    )
    activity_level: ActivityLevel | None = Field(default=None)
    goal: FitnessGoal | None = Field(default=None)
    training_days_per_week: int | None = Field(default=None)
    injuries: list[InjuryStatement] = Field(
        default_factory=list, description="Injuries the user reported in this turn."
    )
    fields_to_revise: list[FieldName] = Field(
        default_factory=list,
        description="Fields the user wants changed but did not restate a value for.",
    )

    @property
    def states_a_profile_field(self) -> bool:
        """Whether the turn answered anything the profile collection loop asks for."""
        dumped = self.model_dump()
        return any(dumped[name] is not None for name in EXTRACTABLE_FIELDS)


class TurnParse(ProfileStatement):
    """Structured output for the turn parser: the routing label plus what the turn stated."""

    intent: Intent = Field(description="One of: coaching, qa, off_topic.")
    preferences: PreferenceStatement = Field(
        default_factory=PreferenceStatement,
        description="What the user said they would rather, if anything.",
    )


@lru_cache
def _build_parser() -> Runnable:
    """The shared turn parser: the structured-output model under the shared retry policy."""
    return with_retry_policy(chat_model().with_structured_output(TurnParse))


async def parse_user_turn(
    user_message: str, fields_in_focus: list[str] | None = None
) -> TurnParse:
    """Classify one user message and extract the profile facts it states, in one call."""

    if not user_message.strip():
        return TurnParse(intent=DEFAULT_INTENT)

    try:
        return await _build_parser().ainvoke(
            build_turn_parser_messages(user_message, fields_in_focus)
        )
    except Exception as error:
        # The collection loop asks again and its retry counter bounds that, so a failed
        # parse costs one more question rather than the whole run.
        logger.exception(
            "turn_parsing_failed", error=str(error), fallback_intent=DEFAULT_INTENT
        )
        return TurnParse(intent=DEFAULT_INTENT)
