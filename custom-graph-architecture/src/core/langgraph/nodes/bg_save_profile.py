"""The ``bg_save_profile`` node: persist the runtime profile without blocking planning."""

from typing import TypedDict

from src.schemas import GraphState
from src.services.profile import save_profile_in_background


class BgSaveProfileUpdate(TypedDict):
    """The state ``bg_save_profile`` writes — nothing; it only starts a side effect."""


async def bg_save_profile(state: GraphState) -> BgSaveProfileUpdate:
    """Fire off the profile persistence write without waiting on it."""

    profile = state.get("profile")
    if profile:
        save_profile_in_background(state["user_id"], profile)
    return {}
