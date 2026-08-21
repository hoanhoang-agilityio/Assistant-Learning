"""The workflow graph"""

from langgraph.graph import END, START, StateGraph

from src.core.langgraph.nodes import blocked, llm_guard, route_after_guard
from src.schemas import GraphState

GUARD_ROUTES: dict[str, str] = {"blocked": "blocked", "pass": END}


def build_graph() -> StateGraph:
    """Assemble the workflow graph."""
    builder = StateGraph(GraphState)

    builder.add_node("llm_guard", llm_guard)
    builder.add_node("blocked", blocked)

    builder.add_edge(START, "llm_guard")
    builder.add_conditional_edges("llm_guard", route_after_guard, GUARD_ROUTES)
    builder.add_edge("blocked", END)

    return builder
