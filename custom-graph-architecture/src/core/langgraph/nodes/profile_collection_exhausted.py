"""The ``profile_collection_exhausted`` node: stop asking once the user has been asked enough times."""

from typing import TypedDict

from langchain_core.messages import AIMessage, AnyMessage

from src.core.langgraph.nodes.request_missing_profile_fields import FIELD_PROMPTS
from src.schemas import GraphState

EXHAUSTED_INTRO = (
    "I still need a few details to create a safe, personalized plan for you, "
    "so I'll pause here rather than make assumptions."
)

EXHAUSTED_MISSING_INTRO = "I still need:"

EXHAUSTED_OUTRO = (
    "No worries — nothing has been saved yet. "
    "Send me these details whenever you're ready, and we'll pick up where we left off!"
)


class ProfileCollectionExhaustedUpdate(TypedDict):
    """The state ``profile_collection_exhausted`` writes."""

    final_message: str
    messages: list[AnyMessage]


def build_exhausted_message(missing_fields: list[str]) -> str:
    """Compose the message that ends a collection loop the user did not complete."""

    if not missing_fields:
        return f"{EXHAUSTED_INTRO}\n\n{EXHAUSTED_OUTRO}"

    bullets = "\n".join(f"- {FIELD_PROMPTS.get(name, name)}" for name in missing_fields)
    return f"{EXHAUSTED_INTRO}\n\n{EXHAUSTED_MISSING_INTRO}\n{bullets}\n\n{EXHAUSTED_OUTRO}"


async def profile_collection_exhausted(
    state: GraphState,
) -> ProfileCollectionExhaustedUpdate:
    """End the run after the user was asked for their profile too many times."""

    message = build_exhausted_message(state.get("missing_fields", []))

    return {"final_message": message, "messages": [AIMessage(content=message)]}
