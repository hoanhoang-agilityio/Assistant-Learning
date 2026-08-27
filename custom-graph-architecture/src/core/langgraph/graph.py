"""The workflow graph"""

from collections.abc import Callable

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.constants.routes import (
    CONTEXT_ROUTES,
    FAITHFULNESS_ROUTES,
    GUARD_ROUTES,
    HITL_ROUTES,
    PARSE_ROUTES,
    PROFILE_ROUTES,
    VERIFICATION_ROUTES,
)
from src.core.langgraph.agents import coach_agent, qa_agent
from src.core.langgraph.nodes import (
    blocked,
    check_profile_complete,
    deterministic_verification,
    finalize_turn,
    guard_input,
    hitl_exhausted,
    hitl_rejected_no_feedback,
    hitl_review,
    load_user_context,
    merge_profile,
    notify_fail,
    off_topic,
    parse_turn,
    persist_preferences,
    persist_profile,
    present_plan,
    profile_collection_exhausted,
    qa_fallback,
    request_missing_profile_fields,
    route_after_context,
    route_after_faithfulness,
    route_after_guard,
    route_after_hitl_review,
    route_after_parse,
    route_after_profile_check,
    route_after_verification,
    verify_faithfulness,
    wait_for_user,
)
from src.core.observability import observed
from src.enums import Node
from src.schemas import GraphState

# Every node the graph runs, paired with the name it is reached by. Listed rather than
# added one call at a time so each one goes through ``observed`` and none can be added
# without the instrumentation the rest of them carry.
NODES: tuple[tuple[Node, Callable], ...] = (
    (Node.GUARD_INPUT, guard_input),
    (Node.BLOCKED, blocked),
    (Node.PARSE_TURN, parse_turn),
    (Node.OFF_TOPIC, off_topic),
    (Node.LOAD_USER_CONTEXT, load_user_context),
    (Node.MERGE_PROFILE, merge_profile),
    (Node.PERSIST_PROFILE, persist_profile),
    (Node.PERSIST_PREFERENCES, persist_preferences),
    (Node.CHECK_PROFILE_COMPLETE, check_profile_complete),
    (Node.REQUEST_MISSING_PROFILE_FIELDS, request_missing_profile_fields),
    (Node.WAIT_FOR_USER, wait_for_user),
    (Node.PROFILE_COLLECTION_EXHAUSTED, profile_collection_exhausted),
    (Node.COACH_AGENT, coach_agent),
    (Node.DETERMINISTIC_VERIFICATION, deterministic_verification),
    (Node.PRESENT_PLAN, present_plan),
    (Node.NOTIFY_FAIL, notify_fail),
    (Node.HITL_REVIEW, hitl_review),
    (Node.HITL_REJECTED_NO_FEEDBACK, hitl_rejected_no_feedback),
    (Node.HITL_EXHAUSTED, hitl_exhausted),
    (Node.QA_AGENT, qa_agent),
    (Node.VERIFY_FAITHFULNESS, verify_faithfulness),
    (Node.QA_FALLBACK, qa_fallback),
    (Node.FINALIZE_TURN, finalize_turn),
)


def build_graph() -> StateGraph:
    """The workflow graph."""
    builder = StateGraph(GraphState)

    for name, node in NODES:
        builder.add_node(name, observed(name, node))

    builder.add_edge(START, Node.GUARD_INPUT)
    builder.add_conditional_edges(Node.GUARD_INPUT, route_after_guard, GUARD_ROUTES)
    builder.add_edge(Node.BLOCKED, END)
    builder.add_conditional_edges(Node.PARSE_TURN, route_after_parse, PARSE_ROUTES)
    builder.add_edge(Node.OFF_TOPIC, END)
    builder.add_edge(Node.LOAD_USER_CONTEXT, Node.MERGE_PROFILE)
    builder.add_edge(Node.MERGE_PROFILE, Node.PERSIST_PROFILE)
    builder.add_edge(Node.PERSIST_PROFILE, Node.PERSIST_PREFERENCES)
    builder.add_conditional_edges(
        Node.PERSIST_PREFERENCES, route_after_context, CONTEXT_ROUTES
    )
    builder.add_conditional_edges(
        Node.CHECK_PROFILE_COMPLETE, route_after_profile_check, PROFILE_ROUTES
    )
    builder.add_edge(Node.REQUEST_MISSING_PROFILE_FIELDS, Node.WAIT_FOR_USER)
    builder.add_edge(Node.WAIT_FOR_USER, Node.PARSE_TURN)
    builder.add_edge(Node.PROFILE_COLLECTION_EXHAUSTED, Node.FINALIZE_TURN)
    builder.add_edge(Node.COACH_AGENT, Node.DETERMINISTIC_VERIFICATION)
    builder.add_conditional_edges(
        Node.DETERMINISTIC_VERIFICATION, route_after_verification, VERIFICATION_ROUTES
    )
    builder.add_edge(Node.PRESENT_PLAN, Node.HITL_REVIEW)
    builder.add_edge(Node.NOTIFY_FAIL, Node.FINALIZE_TURN)
    builder.add_conditional_edges(
        Node.HITL_REVIEW, route_after_hitl_review, HITL_ROUTES
    )
    builder.add_edge(Node.HITL_REJECTED_NO_FEEDBACK, Node.FINALIZE_TURN)
    builder.add_edge(Node.HITL_EXHAUSTED, Node.FINALIZE_TURN)
    builder.add_edge(Node.QA_AGENT, Node.VERIFY_FAITHFULNESS)
    builder.add_conditional_edges(
        Node.VERIFY_FAITHFULNESS, route_after_faithfulness, FAITHFULNESS_ROUTES
    )
    builder.add_edge(Node.QA_FALLBACK, Node.FINALIZE_TURN)
    builder.add_edge(Node.FINALIZE_TURN, END)

    return builder


def build_compiled_graph() -> CompiledStateGraph:
    """The graph for LangGraph Studio; `langgraph dev` injects its own checkpointer."""
    return build_graph().compile()
