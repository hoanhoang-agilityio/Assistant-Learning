"""The ``commit_profile_update`` node: the only place an approved profile overwrite is persisted."""

from typing import TypedDict

from langchain_core.messages import AIMessage, AnyMessage

from src.schemas import GraphState
from src.services.profile import save_profile

PROFILE_UPDATED_MESSAGE = "Got it, I've updated your profile."


class CommitProfileUpdateState(TypedDict):
    """The state ``commit_profile_update`` writes."""

    profile: dict
    messages: list[AnyMessage]


async def commit_profile_update(state: GraphState) -> CommitProfileUpdateState:
    """Apply the overwrite ``hitl_agent`` just approved, and confirm it to the user."""

    payload = state["pending_approval"]["payload"]
    profile = await save_profile(state["user_id"], payload)

    return {
        "profile": profile,
        "messages": [AIMessage(content=PROFILE_UPDATED_MESSAGE)],
    }
