"""The ``hitl_rejected_no_feedback`` node: stop when a rejection gives nothing to revise."""

from typing import TypedDict

from langchain_core.messages import AIMessage, AnyMessage

from src.schemas import GraphState

HITL_REJECTED_NO_FEEDBACK_MESSAGE = (
    "Understood. This plan will not be saved. Without specific feedback, I don't "
    "have enough information to make a meaningful revision, so I'll stop here "
    "rather than make assumptions. When you're ready, please provide the changes "
    "you'd like, and I'll create a new version."
)


class HitlRejectedNoFeedbackUpdate(TypedDict):
    """The state ``hitl_rejected_no_feedback`` writes."""

    messages: list[AnyMessage]


async def hitl_rejected_no_feedback(state: GraphState) -> HitlRejectedNoFeedbackUpdate:
    """End the coaching branch after a rejection that came with no feedback to revise from."""

    return {"messages": [AIMessage(content=HITL_REJECTED_NO_FEEDBACK_MESSAGE)]}
