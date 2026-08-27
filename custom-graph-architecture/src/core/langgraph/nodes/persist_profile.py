"""The ``persist_profile`` node: write the runtime profile to long-term memory."""

from typing import TypedDict

from src.schemas import GraphState
from src.services.profile import save_profile


class PersistProfileUpdate(TypedDict):
    """The state ``persist_profile`` writes — nothing; it only performs a side effect."""


async def persist_profile(state: GraphState) -> PersistProfileUpdate:
    """Persist the merged profile, so the next node's reload cannot read a stale one."""

    profile = state.get("profile")
    if profile:
        await save_profile(state["user_id"], profile)
    return {}
