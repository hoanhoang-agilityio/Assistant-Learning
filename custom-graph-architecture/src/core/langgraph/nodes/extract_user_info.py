"""The ``extract_user_info`` node: fold the current user message into the runtime profile."""

from typing import TypedDict

from langchain_core.messages import AnyMessage, HumanMessage

from src.schemas import GraphState
from src.services.profile import (
    extract_profile_fields,
    merge_profile_updates,
    pending_revision_fields,
)


class ExtractUserInfoUpdate(TypedDict):
    """The state ``extract_user_info`` writes."""

    profile: dict | None
    revision_fields: list[str]


def latest_user_reply(messages: list[AnyMessage]) -> str:
    """Return the text of the most recent user turn."""

    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


async def extract_user_info(state: GraphState) -> ExtractUserInfoUpdate:
    """Extract profile facts and revision requests from the latest message, merged in-memory."""

    reply = latest_user_reply(state["messages"])
    extraction = await extract_profile_fields(
        reply, fields_in_focus=state.get("missing_fields")
    )

    merged = merge_profile_updates(state.get("profile"), extraction)
    revision_fields = pending_revision_fields(
        merged, [*state.get("revision_fields", []), *extraction.fields_to_revise]
    )

    return {"profile": merged, "revision_fields": revision_fields}
