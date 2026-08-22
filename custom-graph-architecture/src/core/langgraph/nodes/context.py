"""The context nodes: ``load_context`` loads the user's data, ``determine_context`` diagnoses it."""

from typing import Literal, TypedDict

from src.schemas import GraphState
from src.services.profile import load_user_context, missing_profile_fields

ContextRoute = Literal["complete", "incomplete"]


class ContextUpdate(TypedDict):
    """The state ``load_context`` writes."""

    profile: dict | None
    plan: dict | None
    context_complete: bool
    missing_fields: list[str]


class MissingFieldsUpdate(TypedDict):
    """The state ``determine_context`` writes."""

    missing_fields: list[str]


async def load_context(state: GraphState) -> ContextUpdate:
    """Load the user's long-term profile and current plan into state."""

    user_id = state["user_id"]
    context = await load_user_context(user_id)

    return {
        "profile": context.profile,
        "plan": context.plan,
        "context_complete": context.is_complete,
        # Cleared rather than left alone: a list from an earlier pass through the
        # interrupt loop must not travel into the planning branch as if still unanswered.
        "missing_fields": [],
    }


async def determine_context(state: GraphState) -> MissingFieldsUpdate:
    """Name the required profile fields still missing, for the request that follows."""

    missing_fields = missing_profile_fields(state.get("profile"))

    return {"missing_fields": missing_fields}


def route_after_context(state: GraphState) -> ContextRoute:
    """Route on whether the loaded profile is good enough to plan from."""

    if state.get("context_complete"):
        return "complete"
    return "incomplete"
