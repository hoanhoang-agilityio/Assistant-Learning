"""The context nodes: ``load_context`` loads the user's data, ``determine_context`` diagnoses it."""

from typing import Literal, TypedDict

from src.core.configs.config import settings
from src.schemas import GraphState
from src.services.profile import load_user_context, missing_profile_fields

ContextRoute = Literal["complete", "incomplete"]
MissingInfoRoute = Literal["ask", "exhausted"]


class ContextUpdate(TypedDict):
    """The state ``load_context`` writes."""

    profile: dict | None
    plan: dict | None
    context_complete: bool
    missing_fields: list[str]
    user_info_retry_count: int


class MissingFieldsUpdate(TypedDict):
    """The state ``determine_context`` writes."""

    missing_fields: list[str]


async def load_context(state: GraphState) -> ContextUpdate:
    """Load the user's long-term profile and current plan into state."""

    user_id = state["user_id"]
    context = await load_user_context(user_id)
    retry_count = state.get("user_info_retry_count", 0)

    if not context.is_complete:
        return {
            "profile": context.profile,
            "plan": context.plan,
            "context_complete": False,
            "missing_fields": [],
            "user_info_retry_count": retry_count,
        }

    # The collection loop is over, so its list and its counter are cleared: left behind,
    # they would travel into the planning branch and exhaust the next round instantly.
    return {
        "profile": context.profile,
        "plan": context.plan,
        "context_complete": True,
        "missing_fields": [],
        "user_info_retry_count": 0,
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


def route_after_determine_context(state: GraphState) -> MissingInfoRoute:
    """Ask for the missing data, or give up once the user has been asked enough times."""

    if state.get("user_info_retry_count", 0) >= settings.USER_INFO_MAX_RETRIES:
        return "exhausted"
    return "ask"
