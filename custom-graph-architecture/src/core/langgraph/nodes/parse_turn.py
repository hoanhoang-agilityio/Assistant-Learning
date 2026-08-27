"""The ``parse_turn`` node: read one user message for its intent and the facts it states."""

from typing import TypedDict

from langchain_core.messages import AnyMessage, HumanMessage

from src.schemas import GraphState, Intent
from src.services.turn import DEFAULT_INTENT, TurnParse, parse_user_turn


class ParseTurnUpdate(TypedDict):
    """The state ``parse_turn`` writes."""

    user_query: str
    intent: Intent
    extracted_facts: dict


def latest_user_reply(messages: list[AnyMessage]) -> str:
    """Return the text of the most recent user turn."""

    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def sticky_intent(state: GraphState, parse: TurnParse) -> Intent:
    """Keep the intent that opened the collection loop while the user is still answering it."""

    previous = state.get("intent")
    if previous and state.get("missing_fields") and parse.states_a_profile_field:
        return previous
    return parse.intent


async def parse_turn(state: GraphState) -> ParseTurnUpdate:
    """Classify the latest message and extract what it says about the user, in one call."""

    message = latest_user_reply(state["messages"]) or state["user_query"]
    parse = await parse_user_turn(message, fields_in_focus=state.get("missing_fields"))

    return {
        "user_query": message,
        "intent": sticky_intent(state, parse),
        "extracted_facts": parse.model_dump(mode="json", exclude={"intent"}),
    }


def route_after_parse(state: GraphState) -> Intent:
    """Route the graph according to the parsed intent."""

    return state.get("intent") or DEFAULT_INTENT
