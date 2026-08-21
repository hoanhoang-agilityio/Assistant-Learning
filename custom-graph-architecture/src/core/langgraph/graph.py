"""The workflow graph"""

from langgraph.graph import END, START, StateGraph

from src.core.langgraph.nodes import (
    blocked,
    classify_intent,
    llm_guard,
    off_topic,
    route_after_guard,
    route_after_intent,
)
from src.schemas import GraphState

GUARD_ROUTES: dict[str, str] = {
    "blocked": "blocked", "pass": "classify_intent"}

INTENT_ROUTES: dict[str, str] = {
    "coaching": END,
    "qa": END,
    "off_topic": "off_topic",
}


def build_graph() -> StateGraph:
    """The workflow graph."""
    builder = StateGraph(GraphState)

    builder.add_node("llm_guard", llm_guard)
    builder.add_node("blocked", blocked)
    builder.add_node("classify_intent", classify_intent)
    builder.add_node("off_topic", off_topic)

    builder.add_edge(START, "llm_guard")
    builder.add_conditional_edges("llm_guard", route_after_guard, GUARD_ROUTES)
    builder.add_conditional_edges(
        "classify_intent", route_after_intent, INTENT_ROUTES)
    builder.add_edge("blocked", END)
    builder.add_edge("off_topic", END)

    return builder
