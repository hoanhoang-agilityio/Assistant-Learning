"""The graph's shape, checked against the edge table in the implementation spec."""

import pytest
from langgraph.graph import END, START

from src.core.langgraph.graph import build_graph

# Nodes implemented so far. The rest of the spec's table arrives with later milestones.
EXPECTED_NODES = {
    "llm_guard",
    "blocked",
    "classify_intent",
    "off_topic",
    "load_context",
    "extract_user_info",
    "check_profile_complete",
    "request_missing_info",
    "wait_for_user",
    "bg_save_profile",
    "user_info_exhausted",
    "coach_agent",
    "deterministic_verification",
    "notify_fail",
    "hitl_review",
    "hitl_rejected_no_feedback",
    "hitl_exhausted",
    "qa_agent",
}

# (from, condition, to) — ``None`` where the edge is unconditional.
EXPECTED_EDGES = {
    (START, None, "llm_guard"),
    ("llm_guard", "blocked", "blocked"),
    ("llm_guard", "pass", "classify_intent"),
    ("classify_intent", "coaching", "load_context"),
    ("classify_intent", "off_topic", "off_topic"),
    ("load_context", None, "extract_user_info"),
    ("extract_user_info", None, "check_profile_complete"),
    ("check_profile_complete", "ask", "request_missing_info"),
    ("check_profile_complete", "exhausted", "user_info_exhausted"),
    ("check_profile_complete", "complete", "bg_save_profile"),
    ("request_missing_info", None, "wait_for_user"),
    ("wait_for_user", None, "extract_user_info"),
    ("bg_save_profile", None, "coach_agent"),
    ("blocked", None, END),
    ("off_topic", None, END),
    ("user_info_exhausted", None, END),
    ("coach_agent", None, "deterministic_verification"),
    ("deterministic_verification", "pass", "hitl_review"),
    ("deterministic_verification", "retry", "coach_agent"),
    ("deterministic_verification", "exhausted", "notify_fail"),
    ("notify_fail", None, END),
    ("hitl_review", "approve", END),
    ("hitl_review", "revise", "coach_agent"),
    ("hitl_review", "no_feedback", "hitl_rejected_no_feedback"),
    ("hitl_review", "exhausted", "hitl_exhausted"),
    ("hitl_rejected_no_feedback", None, END),
    ("hitl_exhausted", None, END),
    ("classify_intent", "qa", "qa_agent"),
    ("qa_agent", None, END),
}

# What ``route_after_verification`` may return, and where each answer goes.
EXPECTED_VERIFICATION_ROUTES = {
    "pass": "hitl_review",
    "retry": "coach_agent",
    "exhausted": "notify_fail",
}

# What ``route_after_hitl_review`` may return, and where each answer goes.
EXPECTED_HITL_ROUTES = {
    "approve": END,
    "revise": "coach_agent",
    "no_feedback": "hitl_rejected_no_feedback",
    "exhausted": "hitl_exhausted",
}


@pytest.fixture(scope="module")
def graph():
    """The compiled graph's own view of its nodes and edges."""
    return build_graph().compile(name="wiring_test").get_graph()


@pytest.fixture(scope="module")
def edges(graph) -> set[tuple[str, str | None, str]]:
    """Every edge as ``(from, condition, to)``.

    LangGraph drops the branch label when it matches the target node's name, so a
    conditional edge with no label is restored to the name it routed on.
    """
    return {
        (
            edge.source,
            (edge.data or edge.target) if edge.conditional else None,
            edge.target,
        )
        for edge in graph.edges
    }


def test_every_implemented_node_is_in_the_graph(graph) -> None:
    """A node that exists but is never added is dead code the tests would still pass."""
    assert EXPECTED_NODES <= set(graph.nodes)


@pytest.mark.parametrize("edge", sorted(EXPECTED_EDGES, key=str))
def test_the_spec_edge_exists(edges, edge: tuple[str, str | None, str]) -> None:
    """Each row of the spec's edge table, for the nodes built so far."""
    assert edge in edges


def test_the_context_branch_has_no_edges_beyond_the_spec(edges) -> None:
    """An extra route out of the collection loop would be a way to skip the profile gate."""
    context_nodes = EXPECTED_NODES - {
        "llm_guard",
        "blocked",
        "classify_intent",
        "off_topic",
    }
    actual = {edge for edge in edges if edge[0] in context_nodes}

    assert actual == {edge for edge in EXPECTED_EDGES if edge[0] in context_nodes}


def test_the_collection_loop_returns_to_extraction_not_the_reload(edges) -> None:
    """A reload here would race the background save with a stale read; extraction skips it."""
    assert ("wait_for_user", None, "extract_user_info") in edges
    assert not [
        edge
        for edge in edges
        if edge[0] == "wait_for_user" and edge[2] != "extract_user_info"
    ]


def test_a_complete_profile_goes_to_a_background_save_then_planning(edges) -> None:
    """The profile gate's whole purpose: a complete profile is what opens the coach branch."""
    assert ("check_profile_complete", "complete", "bg_save_profile") in edges
    assert ("bg_save_profile", None, "coach_agent") in edges


def test_a_generated_plan_is_verified_before_anything_else(edges) -> None:
    """The gate is the only thing between the agent's plan and the user."""
    assert ("coach_agent", None, "deterministic_verification") in edges
    assert not [
        edge
        for edge in edges
        if edge[0] == "coach_agent" and edge[2] != "deterministic_verification"
    ]


def test_a_plan_that_never_verifies_ends_at_the_notification(edges) -> None:
    """The run has to say it gave up; ending silently reads as a plan that never came."""
    assert ("deterministic_verification", "exhausted", "notify_fail") in edges
    assert ("notify_fail", None, END) in edges


def test_the_gate_routes_exactly_the_three_ways_the_spec_names() -> None:
    """Pass, send back, give up: a fourth way out would be a way past the gate."""
    [branch] = build_graph().branches["deterministic_verification"].values()

    assert branch.ends == EXPECTED_VERIFICATION_ROUTES


def test_a_verified_plan_goes_to_the_reviewer(edges) -> None:
    """The gate no longer hands the plan straight to the user; review comes first."""
    assert ("deterministic_verification", "pass", "hitl_review") in edges


def test_the_reviewer_routes_exactly_the_four_ways_the_spec_names() -> None:
    """Approve, revise, no feedback, exhausted: nothing else gets past the reviewer."""
    [branch] = build_graph().branches["hitl_review"].values()

    assert branch.ends == EXPECTED_HITL_ROUTES


def test_a_rejection_with_no_feedback_stops_without_looping(edges) -> None:
    """No feedback means nothing to revise with, so the run ends rather than retrying."""
    assert ("hitl_review", "no_feedback", "hitl_rejected_no_feedback") in edges
    assert ("hitl_rejected_no_feedback", None, END) in edges


def test_a_reviewer_exhausted_by_retries_stops_too(edges) -> None:
    """The revision loop is bounded, just like the verification loop is."""
    assert ("hitl_review", "exhausted", "hitl_exhausted") in edges
    assert ("hitl_exhausted", None, END) in edges
