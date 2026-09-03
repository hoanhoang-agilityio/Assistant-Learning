"""The workflow graph: a supervisor router deciding one agent at a time, in a loop."""

from collections.abc import Callable

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents import (
    coach_agent,
    qa_agent,
    route_after_coach,
    route_after_supervisor,
    route_after_user_agent,
    supervisor,
    user_agent,
)
from src.constants.routes import (
    COACH_ROUTES,
    FAITHFULNESS_ROUTES,
    GUARD_ROUTES,
    PLAN_APPROVAL_ROUTES,
    SUPERVISOR_ROUTES,
    USER_AGENT_ROUTES,
    VERIFICATION_ROUTES,
)
from src.enums import Node
from src.nodes import (
    blocked,
    collect_profile,
    commit_plan,
    deterministic_verification,
    draft_profile,
    guard_input,
    hitl_exhausted,
    hitl_rejected_no_feedback,
    notify_fail,
    plan_approval,
    present_plan,
    qa_fallback,
    route_after_faithfulness,
    route_after_guard,
    route_after_plan_approval,
    route_after_verification,
    verify_faithfulness,
)
from src.observability import observed
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
    (Node.DRAFT_PROFILE, draft_profile),
    (Node.COLLECT_PROFILE, collect_profile),
    (Node.DETERMINISTIC_VERIFICATION, deterministic_verification),
    (Node.PRESENT_PLAN, present_plan),
    (Node.NOTIFY_FAIL, notify_fail),
    (Node.PLAN_APPROVAL, plan_approval),
    (Node.HITL_REJECTED_NO_FEEDBACK, hitl_rejected_no_feedback),
    (Node.HITL_EXHAUSTED, hitl_exhausted),
    (Node.COMMIT_PLAN, commit_plan),
    (Node.QA_AGENT, qa_agent),
    (Node.VERIFY_FAITHFULNESS, verify_faithfulness),
    (Node.QA_FALLBACK, qa_fallback),
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
    builder.add_conditional_edges(Node.COACH_AGENT, route_after_coach, COACH_ROUTES)
    builder.add_edge(Node.DRAFT_PROFILE, Node.COLLECT_PROFILE)
    builder.add_edge(Node.COLLECT_PROFILE, Node.SUPERVISOR)
    builder.add_conditional_edges(
        Node.DETERMINISTIC_VERIFICATION, route_after_verification, VERIFICATION_ROUTES
    )
    builder.add_edge(Node.PRESENT_PLAN, Node.PLAN_APPROVAL)
    builder.add_edge(Node.NOTIFY_FAIL, Node.SUPERVISOR)
    builder.add_conditional_edges(
        Node.PLAN_APPROVAL, route_after_plan_approval, PLAN_APPROVAL_ROUTES
    )
    builder.add_edge(Node.COMMIT_PLAN, Node.SUPERVISOR)
    builder.add_edge(Node.HITL_REJECTED_NO_FEEDBACK, Node.SUPERVISOR)
    builder.add_edge(Node.HITL_EXHAUSTED, Node.SUPERVISOR)
    builder.add_edge(Node.QA_AGENT, Node.VERIFY_FAITHFULNESS)
    builder.add_conditional_edges(
        Node.VERIFY_FAITHFULNESS, route_after_faithfulness, FAITHFULNESS_ROUTES
    )
    builder.add_edge(Node.QA_FALLBACK, Node.SUPERVISOR)

    return builder


def build_compiled_graph() -> CompiledStateGraph:
    """The graph for LangGraph Studio; `langgraph dev` injects its own checkpointer."""
    return build_graph().compile()
