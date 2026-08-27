"""The ``guard_input`` node: scan the incoming query and record the verdict."""

from typing import TypedDict

from src.enums import GuardRoute
from src.schemas import GraphState, is_blocked
from src.services.guard import scan_input


class GuardUpdate(TypedDict):
    """The state ``guard_input`` writes."""

    block_reason: str | None


async def guard_input(state: GraphState) -> GuardUpdate:
    """Scan the user's query and record whether it may proceed."""

    verdict = await scan_input(state["user_query"])
    return {"block_reason": verdict.reason}


def route_after_guard(state: GraphState) -> GuardRoute:
    """Route on the guard verdict."""

    if is_blocked(state):
        return GuardRoute.BLOCKED
    return GuardRoute.PASS
