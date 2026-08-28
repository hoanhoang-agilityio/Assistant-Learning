"""The ``hitl_exhausted`` node: stop once too many revisions still haven't been approved."""

from typing import TypedDict

from langchain_core.messages import AIMessage, AnyMessage

from src.schemas import GraphState

HITL_EXHAUSTED_MESSAGE = (
    "I've tried revising your plan a few times based on your feedback, but I don't want "
    "to keep making changes without being sure I'm getting it right. Nothing has been "
    "saved. When you're ready, just let me know what you'd like to change in a bit more "
    "detail, and I'll take a fresh look at it."
)


class HitlExhaustedUpdate(TypedDict):
    """The state ``hitl_exhausted`` writes."""

    messages: list[AnyMessage]


async def hitl_exhausted(state: GraphState) -> HitlExhaustedUpdate:
    """End the coaching branch after too many rejected revisions were sent back to the coach."""

    return {"messages": [AIMessage(content=HITL_EXHAUSTED_MESSAGE)]}
