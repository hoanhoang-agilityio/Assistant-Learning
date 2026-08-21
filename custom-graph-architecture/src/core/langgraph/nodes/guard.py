"""The ``llm_guard`` node: scan the incoming query and record the verdict."""

from typing import Literal, TypedDict

from src.schemas import GraphState
from src.services.guard import scan_input

GuardRoute = Literal["blocked", "pass"]


class GuardUpdate(TypedDict):
    """The state ``llm_guard`` writes."""

    guard_blocked: bool
    block_reason: str | None


async def llm_guard(state: GraphState) -> GuardUpdate:
    """Scan the user's query and record whether it may proceed."""

    verdict = await scan_input(state["user_query"])
    return {"guard_blocked": verdict.is_blocked, "block_reason": verdict.reason}


def route_after_guard(state: GraphState) -> GuardRoute:
    """Route on the guard verdict."""

    if state["guard_blocked"]:
        return "blocked"
    return "pass"
