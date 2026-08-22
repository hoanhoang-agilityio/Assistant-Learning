"""The ``save_user_data`` node: persist the user's reply before the context is reloaded."""

from typing import TypedDict

from langchain_core.messages import AnyMessage, HumanMessage

from src.schemas import GraphState
from src.services.profile import extract_profile_fields, save_profile


class SaveUserDataUpdate(TypedDict):
    """The state ``save_user_data`` writes."""

    profile: dict | None


def latest_user_reply(messages: list[AnyMessage]) -> str:
    """Return the text of the most recent user turn, which is what ``wait_for_user`` wrote."""

    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


async def save_user_data(state: GraphState) -> SaveUserDataUpdate:
    """Extract profile fields from the user's answer and store them."""

    user_id = state["user_id"]
    reply = latest_user_reply(state["messages"])
    extracted = await extract_profile_fields(reply)

    if not extracted:
        return {"profile": state.get("profile")}

    profile = await save_profile(user_id, extracted)

    return {"profile": profile}
