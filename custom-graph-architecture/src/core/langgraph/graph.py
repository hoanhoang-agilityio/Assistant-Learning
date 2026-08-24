"""The workflow graph"""

from langgraph.graph import END, START, StateGraph

from src.core.langgraph.agents import coach_agent
from src.core.langgraph.nodes import (
    blocked,
    classify_intent,
    determine_context,
    deterministic_verification,
    llm_guard,
    load_context,
    notify_fail,
    off_topic,
    request_missing_info,
    route_after_context,
    route_after_determine_context,
    route_after_guard,
    route_after_intent,
    route_after_verification,
    save_user_data,
    user_info_exhausted,
    wait_for_user,
    write_todo,
)
from src.schemas import GraphState

GUARD_ROUTES: dict[str, str] = {"blocked": "blocked", "pass": "classify_intent"}

INTENT_ROUTES: dict[str, str] = {
    "coaching": "load_context",
    "qa": END,
    "off_topic": "off_topic",
}

CONTEXT_ROUTES: dict[str, str] = {
    "complete": "write_todo",
    "incomplete": "determine_context",
}

MISSING_INFO_ROUTES: dict[str, str] = {
    "ask": "request_missing_info",
    "exhausted": "user_info_exhausted",
}

VERIFICATION_ROUTES: dict[str, str] = {
    "pass": END,
    "retry": "coach_agent",
    "exhausted": "notify_fail",
}


def build_graph() -> StateGraph:
    """The workflow graph."""
    builder = StateGraph(GraphState)

    builder.add_node("llm_guard", llm_guard)
    builder.add_node("blocked", blocked)
    builder.add_node("classify_intent", classify_intent)
    builder.add_node("off_topic", off_topic)
    builder.add_node("load_context", load_context)
    builder.add_node("determine_context", determine_context)
    builder.add_node("request_missing_info", request_missing_info)
    builder.add_node("wait_for_user", wait_for_user)
    builder.add_node("save_user_data", save_user_data)
    builder.add_node("user_info_exhausted", user_info_exhausted)
    builder.add_node("write_todo", write_todo)
    builder.add_node("coach_agent", coach_agent)
    builder.add_node("deterministic_verification", deterministic_verification)
    builder.add_node("notify_fail", notify_fail)

    builder.add_edge(START, "llm_guard")
    builder.add_conditional_edges("llm_guard", route_after_guard, GUARD_ROUTES)
    builder.add_conditional_edges("classify_intent", route_after_intent, INTENT_ROUTES)
    builder.add_conditional_edges("load_context", route_after_context, CONTEXT_ROUTES)
    builder.add_conditional_edges(
        "determine_context", route_after_determine_context, MISSING_INFO_ROUTES
    )
    builder.add_edge("request_missing_info", "wait_for_user")
    builder.add_edge("wait_for_user", "save_user_data")
    builder.add_edge("save_user_data", "load_context")
    builder.add_edge("blocked", END)
    builder.add_edge("off_topic", END)
    builder.add_edge("user_info_exhausted", END)
    builder.add_edge("notify_fail", END)
    builder.add_edge("write_todo", "coach_agent")
    builder.add_edge("coach_agent", "deterministic_verification")
    builder.add_conditional_edges(
        "deterministic_verification", route_after_verification, VERIFICATION_ROUTES
    )

    return builder
