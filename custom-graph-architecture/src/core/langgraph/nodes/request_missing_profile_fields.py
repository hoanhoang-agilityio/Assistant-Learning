"""The ``request_missing_profile_fields`` node: ask the user for the profile fields still missing."""

from typing import TypedDict

from langchain_core.messages import AIMessage, AnyMessage

from src.schemas import GraphState
from src.services.profile import REQUIRED_PROFILE_FIELDS

REQUEST_INTRO = "To create a plan that works for you, I just need a few details first:"

REQUEST_OUTRO = "You can send everything in one message — whatever is easiest for you!"

FIELD_PROMPTS: dict[str, str] = {
    "age": "your age",
    "sex": "your sex (male or female)",
    "height_cm": "your height in cm",
    "current_weight_kg": "your current weight in kg",
    "target_weight_kg": "your goal weight in kg",
    "activity_level": (
        "your usual activity level "
        "(sedentary, lightly active, moderately active, very active, or extra active)"
    ),
    "goal": (
        "your main fitness goal "
        "(fat loss, muscle gain, maintenance, strength, or general fitness)"
    ),
    "training_days_per_week": "how many days per week you'd like to train (1-7)",
}


class MissingInfoRequestUpdate(TypedDict):
    """The state ``request_missing_profile_fields`` writes."""

    messages: list[AnyMessage]
    user_info_retry_count: int


def build_missing_info_request(missing_fields: list[str]) -> str:
    """Compose the question that asks for the named profile fields."""

    fields = missing_fields or list(REQUIRED_PROFILE_FIELDS)
    bullets = "\n".join(f"- {FIELD_PROMPTS.get(name, name)}" for name in fields)

    return f"{REQUEST_INTRO}\n{bullets}\n\n{REQUEST_OUTRO}"


async def request_missing_profile_fields(state: GraphState) -> MissingInfoRequestUpdate:
    """Ask the user for the missing profile fields before the run suspends."""

    request = build_missing_info_request(state.get("missing_fields", []))

    # Counted here rather than on the way back in, so the limit counts questions actually
    # put to the user — a reply that never arrives still spends an attempt.
    return {
        "messages": [AIMessage(content=request)],
        "user_info_retry_count": state.get("user_info_retry_count", 0) + 1,
    }
