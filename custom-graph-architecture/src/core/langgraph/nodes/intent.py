"""The ``classify_intent`` node: route clean requests into coaching, QA or off-topic."""

from typing import Literal, TypedDict

from src.schemas import GraphState, Intent
from src.services.intent import DEFAULT_INTENT, classify_user_intent

IntentRoute = Literal["coaching", "qa", "off_topic"]


class IntentUpdate(TypedDict):
    """The state ``classify_intent`` writes."""

    intent: Intent


async def classify_intent(state: GraphState) -> IntentUpdate:
    """Classify the current user query into one of the graph's top-level intents."""
    intent = await classify_user_intent(state["user_query"])
    return {"intent": intent}


def route_after_intent(state: GraphState) -> IntentRoute:
    """Route the graph according to the classified intent."""
    intent = state.get("intent") or DEFAULT_INTENT
    return intent
