"""The ``off_topic`` node: decline unrelated requests and stop the run."""

from typing import TypedDict

from langchain_core.messages import AIMessage, AnyMessage

from src.schemas import GraphState

OFF_TOPIC_MESSAGE = (
    "I'm here to help with fitness training, nutrition, recovery, and injury-aware exercise guidance. "
    "This request is outside what I can help with, but feel free to ask me something fitness-related!"
)


class OffTopicResponseUpdate(TypedDict):
    """The state ``off_topic`` writes."""

    final_message: str
    messages: list[AnyMessage]


async def off_topic(state: GraphState) -> OffTopicResponseUpdate:
    """End the run with a fixed in-domain refusal for unrelated requests."""
    del state
    return {
        "final_message": OFF_TOPIC_MESSAGE,
        "messages": [AIMessage(content=OFF_TOPIC_MESSAGE)],
    }
