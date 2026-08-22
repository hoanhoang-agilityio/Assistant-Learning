"""The ``wait_for_user`` node: suspend the run until the user supplies the missing data."""

from typing import Any, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.types import interrupt

from src.core.langgraph.nodes.request_missing_info import build_missing_info_request
from src.schemas import GraphState

MISSING_INFO_INTERRUPT = "missing_profile_fields"


class MissingInfoInterrupt(TypedDict):
    """The payload the caller receives while the run is suspended here."""

    type: str
    missing_fields: list[str]
    message: str


class WaitForUserUpdate(TypedDict):
    """The state ``wait_for_user`` writes once the user answers."""

    messages: list[AnyMessage]


def _as_text(reply: Any) -> str:
    """Render whatever the caller resumed with as conversation text."""

    if isinstance(reply, str):
        return reply.strip()
    return str(reply)


async def wait_for_user(state: GraphState) -> WaitForUserUpdate:
    """Pause the graph, then record the user's answer as the next turn of the conversation."""

    missing_fields = state.get("missing_fields", [])
    reply = interrupt(
        MissingInfoInterrupt(
            type=MISSING_INFO_INTERRUPT,
            missing_fields=missing_fields,
            message=build_missing_info_request(missing_fields),
        )
    )

    return {"messages": [HumanMessage(content=_as_text(reply))]}
