"""The ``hitl_exhausted`` node: stop once too many revisions still haven't been approved."""

from typing import TypedDict

from langchain_core.messages import AIMessage, AnyMessage

from src.schemas import GraphState

HITL_EXHAUSTED_MESSAGE = (
    "I've revised this plan a few times now based on your feedback, but I don't want to "
    "keep guessing without getting it right. Nothing has been saved. Whenever you're "
    "ready, start a new request and be as specific as you can about what needs to "
    "change, and I'll give it a fresh try."
)


class HitlExhaustedUpdate(TypedDict):
    """The state ``hitl_exhausted`` writes."""

    final_message: str
    messages: list[AnyMessage]


async def hitl_exhausted(state: GraphState) -> HitlExhaustedUpdate:
    """End the run after too many rejected revisions were sent back to the coach."""

    return {
        "final_message": HITL_EXHAUSTED_MESSAGE,
        "messages": [AIMessage(content=HITL_EXHAUSTED_MESSAGE)],
    }
