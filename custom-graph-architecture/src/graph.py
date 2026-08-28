"""The workflow graph: a supervisor router deciding one agent at a time, in a loop."""

from collections.abc import Callable

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents import (
    coach_agent,
    qa_agent,
    route_after_supervisor,
    route_after_user_agent,
    supervisor,
    user_agent,
)
from src.constants.routes import (
    FAITHFULNESS_ROUTES,
    GUARD_ROUTES,
    HITL_AGENT_ROUTES,
    SUPERVISOR_ROUTES,
    USER_AGENT_ROUTES,
    VERIFICATION_ROUTES,
)
from src.core.observability import observed
from src.enums import Node
from src.nodes import (
    blocked,
    commit_plan,
    commit_profile_update,
    deterministic_verification,
    guard_input,
    hitl_agent,
    hitl_exhausted,
    hitl_rejected_no_feedback,
    notify_fail,
    present_plan,
    qa_fallback,
    route_after_faithfulness,
    route_after_guard,
    route_after_hitl,
    route_after_verification,
    summarize,
    verify_faithfulness,
)
from src.schemas import GraphState

# Every node the graph runs, paired with the name it is reached by. Listed rather than
# added one call at a time so each one goes through ``observed`` and none can be added
# without the instrumentation the rest of them carry.
NODES: tuple[tuple[Node, Callable], ...] = (
    (Node.GUARD_INPUT, guard_input),
    (Node.BLOCKED, blocked),
    (Node.SUPERVISOR, supervisor),
    (Node.USER_AGENT, user_agent),
    (Node.COACH_AGENT, coach_agent),
    (Node.DETERMINISTIC_VERIFICATION, deterministic_verification),
    (Node.PRESENT_PLAN, present_plan),
    (Node.NOTIFY_FAIL, notify_fail),
    (Node.HITL_AGENT, hitl_agent),
    (Node.HITL_REJECTED_NO_FEEDBACK, hitl_rejected_no_feedback),
    (Node.HITL_EXHAUSTED, hitl_exhausted),
    (Node.COMMIT_PLAN, commit_plan),
    (Node.COMMIT_PROFILE_UPDATE, commit_profile_update),
    (Node.QA_AGENT, qa_agent),
    (Node.VERIFY_FAITHFULNESS, verify_faithfulness),
    (Node.QA_FALLBACK, qa_fallback),
    (Node.SUMMARIZE, summarize),
)


def build_graph() -> StateGraph:
    """The workflow graph."""
    builder = StateGraph(GraphState)

    for name, node in NODES:
        builder.add_node(name, observed(name, node))

    builder.add_edge(START, Node.GUARD_INPUT)
    builder.add_conditional_edges(Node.GUARD_INPUT, route_after_guard, GUARD_ROUTES)
    builder.add_edge(Node.BLOCKED, END)
    builder.add_conditional_edges(
        Node.SUPERVISOR, route_after_supervisor, SUPERVISOR_ROUTES
    )
    builder.add_conditional_edges(
        Node.USER_AGENT, route_after_user_agent, USER_AGENT_ROUTES
    )
    builder.add_edge(Node.COACH_AGENT, Node.DETERMINISTIC_VERIFICATION)
    builder.add_conditional_edges(
        Node.DETERMINISTIC_VERIFICATION, route_after_verification, VERIFICATION_ROUTES
    )
    builder.add_edge(Node.PRESENT_PLAN, Node.HITL_AGENT)
    builder.add_edge(Node.NOTIFY_FAIL, Node.SUMMARIZE)
    builder.add_conditional_edges(Node.HITL_AGENT, route_after_hitl, HITL_AGENT_ROUTES)
    builder.add_edge(Node.COMMIT_PLAN, Node.SUMMARIZE)
    builder.add_edge(Node.HITL_REJECTED_NO_FEEDBACK, Node.SUMMARIZE)
    builder.add_edge(Node.HITL_EXHAUSTED, Node.SUMMARIZE)
    builder.add_edge(Node.COMMIT_PROFILE_UPDATE, Node.SUMMARIZE)
    builder.add_edge(Node.QA_AGENT, Node.VERIFY_FAITHFULNESS)
    builder.add_conditional_edges(
        Node.VERIFY_FAITHFULNESS, route_after_faithfulness, FAITHFULNESS_ROUTES
    )
    builder.add_edge(Node.QA_FALLBACK, Node.SUMMARIZE)
    builder.add_edge(Node.SUMMARIZE, Node.SUPERVISOR)

    return builder


def build_compiled_graph() -> CompiledStateGraph:
    """The graph for LangGraph Studio; `langgraph dev` injects its own checkpointer."""
    return build_graph().compile()
