"""The context nodes: ``load_user_context`` loads the user's data, ``check_profile_complete`` gates it."""

from typing import TypedDict

from src.core.configs.config import settings
from src.enums import (
    Intent,
    ProfileRoute,
)
from src.schemas import GraphState
from src.services.profile import load_user_context as read_user_context
from src.services.profile import missing_profile_fields


class ContextUpdate(TypedDict):
    """The state ``load_user_context`` writes."""

    profile: dict | None
    plan: dict | None


class ProfileCompleteUpdate(TypedDict):
    """The state ``check_profile_complete`` writes."""

    context_complete: bool
    missing_fields: list[str]
    user_info_retry_count: int


async def load_user_context(state: GraphState) -> ContextUpdate:
    """Load the user's persisted profile and plan into runtime state, once per run."""

    context = await read_user_context(state["user_id"])
    return {"profile": context.profile, "plan": context.plan}


def route_after_context(state: GraphState) -> Intent:
    """Route on the intent parsed before the context was loaded, without asking again."""

    if state.get("intent") == Intent.COACHING:
        return Intent.COACHING
    return Intent.QA


async def check_profile_complete(state: GraphState) -> ProfileCompleteUpdate:
    """Decide whether the merged runtime profile has everything the coach agent needs."""

    profile = state.get("profile")
    required_missing = missing_profile_fields(profile)
    revision_missing = [
        name
        for name in state.get("revision_fields", [])
        if name not in required_missing
    ]
    missing = required_missing + revision_missing
    retry_count = state.get("user_info_retry_count", 0)

    if not missing:
        return {
            "context_complete": True,
            "missing_fields": [],
            "user_info_retry_count": 0,
        }

    return {
        "context_complete": False,
        "missing_fields": missing,
        "user_info_retry_count": retry_count,
    }


def route_after_profile_check(state: GraphState) -> ProfileRoute:
    """Route on completeness, then on whether the collection loop still has room to ask."""

    if state.get("context_complete"):
        return ProfileRoute.COMPLETE
    if state.get("user_info_retry_count", 0) >= settings.USER_INFO_MAX_RETRIES:
        return ProfileRoute.EXHAUSTED
    return ProfileRoute.ASK
