"""The graph's shape: every edge the workflow is allowed to take, and no others."""

import pytest
from langgraph.graph import END, START

from src.core.langgraph.graph import build_graph
from src.schemas import Node

EXPECTED_NODES = {node.value for node in Node}

# (from, condition, to) — ``None`` where the edge is unconditional. Two branch labels that
# lead to the same node are drawn as one edge, so the label set of each router is asserted
# against ``branches`` instead, in ``test_each_router_answers_exactly_the_ways_named``.
EXPECTED_EDGES = {
    (START, None, Node.GUARD_INPUT),
    (Node.GUARD_INPUT, "blocked", Node.BLOCKED),
    (Node.GUARD_INPUT, "pass", Node.PARSE_TURN),
    (Node.BLOCKED, None, END),
    (Node.PARSE_TURN, "coaching", Node.LOAD_USER_CONTEXT),
    (Node.PARSE_TURN, "off_topic", Node.OFF_TOPIC),
    (Node.OFF_TOPIC, None, END),
    (Node.LOAD_USER_CONTEXT, None, Node.MERGE_PROFILE),
    (Node.MERGE_PROFILE, None, Node.PERSIST_PROFILE),
    (Node.PERSIST_PROFILE, "coaching", Node.CHECK_PROFILE_COMPLETE),
    (Node.PERSIST_PROFILE, "qa", Node.QA_AGENT),
    (Node.CHECK_PROFILE_COMPLETE, "ask", Node.REQUEST_MISSING_PROFILE_FIELDS),
    (Node.CHECK_PROFILE_COMPLETE, "exhausted", Node.PROFILE_COLLECTION_EXHAUSTED),
    (Node.CHECK_PROFILE_COMPLETE, "complete", Node.COACH_AGENT),
    (Node.REQUEST_MISSING_PROFILE_FIELDS, None, Node.WAIT_FOR_USER),
    (Node.WAIT_FOR_USER, None, Node.PARSE_TURN),
    (Node.PROFILE_COLLECTION_EXHAUSTED, None, Node.FINALIZE_TURN),
    (Node.COACH_AGENT, None, Node.DETERMINISTIC_VERIFICATION),
    (Node.DETERMINISTIC_VERIFICATION, "pass", Node.HITL_REVIEW),
    (Node.DETERMINISTIC_VERIFICATION, "retry", Node.COACH_AGENT),
    (Node.DETERMINISTIC_VERIFICATION, "exhausted", Node.NOTIFY_FAIL),
    (Node.NOTIFY_FAIL, None, Node.FINALIZE_TURN),
    (Node.HITL_REVIEW, "approve", Node.FINALIZE_TURN),
    (Node.HITL_REVIEW, "revise", Node.COACH_AGENT),
    (Node.HITL_REVIEW, "no_feedback", Node.HITL_REJECTED_NO_FEEDBACK),
    (Node.HITL_REVIEW, "exhausted", Node.HITL_EXHAUSTED),
    (Node.HITL_REJECTED_NO_FEEDBACK, None, Node.FINALIZE_TURN),
    (Node.HITL_EXHAUSTED, None, Node.FINALIZE_TURN),
    (Node.QA_AGENT, None, Node.VERIFY_FAITHFULNESS),
    (Node.VERIFY_FAITHFULNESS, "pass", Node.FINALIZE_TURN),
    (Node.VERIFY_FAITHFULNESS, "retry", Node.QA_AGENT),
    (Node.VERIFY_FAITHFULNESS, "fallback", Node.QA_FALLBACK),
    (Node.QA_FALLBACK, None, Node.FINALIZE_TURN),
    (Node.FINALIZE_TURN, None, END),
}

# What each router may answer, and where each answer goes.
EXPECTED_ROUTES: dict[Node, dict[str, str]] = {
    Node.PARSE_TURN: {
        "coaching": Node.LOAD_USER_CONTEXT,
        "qa": Node.LOAD_USER_CONTEXT,
        "off_topic": Node.OFF_TOPIC,
    },
    Node.PERSIST_PROFILE: {
        "coaching": Node.CHECK_PROFILE_COMPLETE,
        "qa": Node.QA_AGENT,
    },
    Node.CHECK_PROFILE_COMPLETE: {
        "complete": Node.COACH_AGENT,
        "ask": Node.REQUEST_MISSING_PROFILE_FIELDS,
        "exhausted": Node.PROFILE_COLLECTION_EXHAUSTED,
    },
    Node.DETERMINISTIC_VERIFICATION: {
        "pass": Node.HITL_REVIEW,
        "retry": Node.COACH_AGENT,
        "exhausted": Node.NOTIFY_FAIL,
    },
    Node.HITL_REVIEW: {
        "approve": Node.FINALIZE_TURN,
        "revise": Node.COACH_AGENT,
        "no_feedback": Node.HITL_REJECTED_NO_FEEDBACK,
        "exhausted": Node.HITL_EXHAUSTED,
    },
    Node.VERIFY_FAITHFULNESS: {
        "pass": Node.FINALIZE_TURN,
        "retry": Node.QA_AGENT,
        "fallback": Node.QA_FALLBACK,
    },
}

# Every way a run can stop producing work. All but the two refusals converge on one node.
TERMINAL_SOURCES = {
    Node.PROFILE_COLLECTION_EXHAUSTED,
    Node.NOTIFY_FAIL,
    Node.HITL_REJECTED_NO_FEEDBACK,
    Node.HITL_EXHAUSTED,
    Node.QA_FALLBACK,
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


def test_every_named_node_is_in_the_graph(graph) -> None:
    """A node that exists but is never added is dead code the tests would still pass."""
    assert EXPECTED_NODES == set(graph.nodes) - {START, END}


@pytest.mark.parametrize("edge", sorted(EXPECTED_EDGES, key=str))
def test_the_expected_edge_exists(edges, edge: tuple[str, str | None, str]) -> None:
    """Each edge of the workflow, one test each."""
    assert edge in edges


def test_the_graph_has_no_edges_beyond_these(edges) -> None:
    """An extra route is a way past a gate; the set is closed, not a lower bound."""
    assert edges == EXPECTED_EDGES


@pytest.mark.parametrize("node", sorted(EXPECTED_ROUTES, key=str))
def test_each_router_answers_exactly_the_ways_named(node: Node) -> None:
    """One more branch out of a router would be one more way past what it guards."""
    [branch] = build_graph().branches[node].values()

    assert branch.ends == EXPECTED_ROUTES[node]


# --- The invariants the shape exists to hold ----------------------------------------------


def test_the_turn_is_parsed_once_and_the_router_never_classifies_again(edges) -> None:
    """Intent is decided in ``parse_turn``; ``route_after_context`` only reads it back."""
    assert (Node.GUARD_INPUT, "pass", Node.PARSE_TURN) in edges
    assert not [
        edge
        for edge in edges
        if edge[2] == Node.PARSE_TURN
        and edge[0] != Node.WAIT_FOR_USER
        and edge[0] != Node.GUARD_INPUT
    ]


def test_both_working_branches_load_the_user_the_same_way(edges) -> None:
    """QA answers off the same profile and plan coaching plans from, loaded once."""
    [branch] = build_graph().branches[Node.PARSE_TURN].values()

    assert branch.ends["coaching"] == Node.LOAD_USER_CONTEXT
    assert branch.ends["qa"] == Node.LOAD_USER_CONTEXT
    assert not [
        edge
        for edge in edges
        if edge[0] == Node.PARSE_TURN and edge[2] == Node.QA_AGENT
    ]


def test_the_profile_is_merged_and_persisted_before_either_branch_runs(edges) -> None:
    """One writer, one write, both ahead of the fork — so no branch reads a stale profile."""
    assert (Node.LOAD_USER_CONTEXT, None, Node.MERGE_PROFILE) in edges
    assert (Node.MERGE_PROFILE, None, Node.PERSIST_PROFILE) in edges
    assert not [
        edge
        for edge in edges
        if edge[0] == Node.MERGE_PROFILE and edge[2] != Node.PERSIST_PROFILE
    ]


def test_the_collection_loop_reparses_the_answer_it_waited_for(edges) -> None:
    """Routing the resume anywhere past ``parse_turn`` leaves the reply unread forever."""
    assert (Node.WAIT_FOR_USER, None, Node.PARSE_TURN) in edges
    assert not [
        edge
        for edge in edges
        if edge[0] == Node.WAIT_FOR_USER and edge[2] != Node.PARSE_TURN
    ]


def test_a_generated_plan_is_verified_before_anything_else(edges) -> None:
    """The gate is the only thing between the agent's plan and the reviewer."""
    assert (Node.COACH_AGENT, None, Node.DETERMINISTIC_VERIFICATION) in edges
    assert not [
        edge
        for edge in edges
        if edge[0] == Node.COACH_AGENT and edge[2] != Node.DETERMINISTIC_VERIFICATION
    ]


def test_an_answer_is_scored_before_it_reaches_the_user(edges) -> None:
    """The faithfulness gate is the only thing between the agent's answer and the user."""
    assert (Node.QA_AGENT, None, Node.VERIFY_FAITHFULNESS) in edges
    assert not [
        edge
        for edge in edges
        if edge[0] == Node.QA_AGENT and edge[2] != Node.VERIFY_FAITHFULNESS
    ]


@pytest.mark.parametrize("node", sorted(TERMINAL_SOURCES, key=str))
def test_every_finished_branch_converges_on_one_node(edges, node: Node) -> None:
    """``finalize_turn`` is where a turn persists and settles its reply — no branch skips it."""
    assert (node, None, Node.FINALIZE_TURN) in edges


def test_only_the_two_refusals_end_without_finalizing(edges) -> None:
    """A blocked or off-topic turn produced nothing to persist and nothing to settle."""
    assert {edge[0] for edge in edges if edge[2] == END} == {
        Node.BLOCKED,
        Node.OFF_TOPIC,
        Node.FINALIZE_TURN,
    }
