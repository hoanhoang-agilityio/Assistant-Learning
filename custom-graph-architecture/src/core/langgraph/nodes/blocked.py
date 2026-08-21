"""The ``blocked`` node: return the guard's reason and stop the run."""

from typing import TypedDict

from langchain_core.messages import AIMessage, AnyMessage

from src.schemas import GraphState
from src.services.guard import DEFAULT_BLOCK_REASON


class BlockedUpdate(TypedDict):
    """The state ``blocked`` writes."""

    final_message: str
    messages: list[AnyMessage]


async def blocked(state: GraphState) -> BlockedUpdate:
    """End the run with the reason the guard rejected the query."""
    reason = state["block_reason"] or DEFAULT_BLOCK_REASON

    return {"final_message": reason, "messages": [AIMessage(content=reason)]}
