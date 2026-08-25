"""The workflow graph"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.core.langgraph.agents import coach_agent
from src.core.langgraph.nodes import (
    bg_save_profile,
    blocked,
    check_profile_complete,
    classify_intent,
    deterministic_verification,
    extract_user_info,
    hitl_exhausted,
    hitl_rejected_no_feedback,
    hitl_review,
    llm_guard,
    load_context,
    notify_fail,
    off_topic,
    request_missing_info,
    route_after_guard,
    route_after_hitl_review,
    route_after_intent,
    route_after_profile_check,
    route_after_verification,
    user_info_exhausted,
    wait_for_user,
)
from src.schemas import GraphState

GUARD_ROUTES: dict[str, str] = {"blocked": "blocked", "pass": "classify_intent"}

INTENT_ROUTES: dict[str, str] = {
    "coaching": "load_context",
    "qa": END,
    "off_topic": "off_topic",
}

PROFILE_ROUTES: dict[str, str] = {
    "complete": "bg_save_profile",
    "ask": "request_missing_info",
    "exhausted": "user_info_exhausted",
}

VERIFICATION_ROUTES: dict[str, str] = {
    "pass": "hitl_review",
    "retry": "coach_agent",
    "exhausted": "notify_fail",
}

HITL_ROUTES: dict[str, str] = {
    "approve": END,
    "revise": "coach_agent",
    "no_feedback": "hitl_rejected_no_feedback",
    "exhausted": "hitl_exhausted",
}


def build_graph() -> StateGraph:
    """The workflow graph."""
    builder = StateGraph(GraphState)

    builder.add_node("llm_guard", llm_guard)
    builder.add_node("blocked", blocked)
    builder.add_node("classify_intent", classify_intent)
    builder.add_node("off_topic", off_topic)
    builder.add_node("load_context", load_context)
    builder.add_node("extract_user_info", extract_user_info)
    builder.add_node("check_profile_complete", check_profile_complete)
    builder.add_node("request_missing_info", request_missing_info)
    builder.add_node("wait_for_user", wait_for_user)
    builder.add_node("bg_save_profile", bg_save_profile)
    builder.add_node("user_info_exhausted", user_info_exhausted)
    builder.add_node("coach_agent", coach_agent)
    builder.add_node("deterministic_verification", deterministic_verification)
    builder.add_node("notify_fail", notify_fail)
    builder.add_node("hitl_review", hitl_review)
    builder.add_node("hitl_rejected_no_feedback", hitl_rejected_no_feedback)
    builder.add_node("hitl_exhausted", hitl_exhausted)

    builder.add_edge(START, "llm_guard")
    builder.add_conditional_edges("llm_guard", route_after_guard, GUARD_ROUTES)
    builder.add_conditional_edges("classify_intent", route_after_intent, INTENT_ROUTES)
    builder.add_edge("load_context", "extract_user_info")
    builder.add_edge("extract_user_info", "check_profile_complete")
    builder.add_conditional_edges(
        "check_profile_complete", route_after_profile_check, PROFILE_ROUTES
    )
    builder.add_edge("request_missing_info", "wait_for_user")
    builder.add_edge("wait_for_user", "extract_user_info")
    builder.add_edge("bg_save_profile", "coach_agent")
    builder.add_edge("blocked", END)
    builder.add_edge("off_topic", END)
    builder.add_edge("user_info_exhausted", END)
    builder.add_edge("notify_fail", END)
    builder.add_edge("coach_agent", "deterministic_verification")
    builder.add_conditional_edges(
        "deterministic_verification", route_after_verification, VERIFICATION_ROUTES
    )
    builder.add_conditional_edges("hitl_review", route_after_hitl_review, HITL_ROUTES)
    builder.add_edge("hitl_rejected_no_feedback", END)
    builder.add_edge("hitl_exhausted", END)

    return builder


def build_compiled_graph() -> CompiledStateGraph:
    """The graph for LangGraph Studio; `langgraph dev` injects its own checkpointer."""
    return build_graph().compile()
