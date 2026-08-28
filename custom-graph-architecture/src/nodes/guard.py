"""The ``guard_input`` node: scan the incoming query and record the verdict."""

from typing import TypedDict

from langchain_core.messages import AnyMessage, HumanMessage

from src.enums import GuardRoute
from src.schemas import GraphState, is_blocked
from src.services.guard import scan_input


class GuardUpdate(TypedDict):
    """The state ``guard_input`` writes."""

    block_reason: str | None


def _latest_user_text(messages: list[AnyMessage]) -> str:
    """The most recent human turn, which is what the guard scans."""

    for message in reversed(messages):
        if isinstance(message, HumanMessage) and isinstance(message.content, str):
            return message.content

    return ""


async def guard_input(state: GraphState) -> GuardUpdate:
    """Scan the user's latest message and record whether it may proceed."""

    verdict = await scan_input(_latest_user_text(state["messages"]))
    return {"block_reason": verdict.reason}


def route_after_guard(state: GraphState) -> GuardRoute:
    """Route on the guard verdict."""

    if is_blocked(state):
        return GuardRoute.BLOCKED
    return GuardRoute.PASS
