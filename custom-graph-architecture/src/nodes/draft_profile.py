"""The ``draft_profile`` node: read the facts the user already stated, before the form asks for them."""

from typing import TypedDict

from src.schemas import GraphState
from src.services.profile_draft import draft_profile as read_draft


class DraftProfileUpdate(TypedDict):
    """The state ``draft_profile`` writes."""

    profile_draft: dict


async def draft_profile(state: GraphState) -> DraftProfileUpdate:
    """Pull the profile fields the conversation already states into a draft for the form."""

    return {"profile_draft": await read_draft(state["messages"])}
