"""The ``load_context`` node: fetch the user's stored profile and plan before planning."""

from typing import Literal, TypedDict

from src.schemas import GraphState
from src.services.profile import load_user_context
from src.utils.logging import logger

ContextRoute = Literal["complete", "incomplete"]


class ContextUpdate(TypedDict):
    """The state ``load_context`` writes."""

    profile: dict | None
    plan: dict | None
    context_complete: bool


async def load_context(state: GraphState) -> ContextUpdate:
    """Load the user's long-term profile and current plan into state."""

    user_id = state["user_id"]
    context = await load_user_context(user_id)

    logger.info(
        "context_loaded",
        user_id=user_id,
        has_profile=context.profile is not None,
        has_plan=context.plan is not None,
        missing_fields=context.missing_fields,
    )
    return {
        "profile": context.profile,
        "plan": context.plan,
        "context_complete": context.is_complete,
    }


def route_after_context(state: GraphState) -> ContextRoute:
    """Route on whether the loaded profile is good enough to plan from."""

    if state.get("context_complete"):
        return "complete"
    return "incomplete"
